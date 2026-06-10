import uuid
from collections.abc import AsyncIterator
from http import HTTPStatus

import pytest

pytest.importorskip("aiosqlite")
pytest.importorskip("pytest_asyncio")
pytest.importorskip("sqlalchemy")

import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.enums import ErrorCode, LedgerEntryType, TransferStatus, UserRole
from app.db import Base
from app.models.tables import Asset, LedgerEntry, LedgerTransaction, User
from app.services import ledger
from app.services.transfer_service import create_transfer

SEPOLIA_ETH_MAX = 1_000_000_000_000_000
TEST_HASH = "hash"


def _user(email: str, hd_index: int) -> User:
    return User(
        email=email,
        password_hash=TEST_HASH,
        role=UserRole.USER.value,
        hd_index=hd_index,
    )


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


@pytest.mark.asyncio
async def test_transfer_posts_one_double_entry_transaction(session: AsyncSession) -> None:
    asset = Asset(
        id=uuid.uuid4(),
        chain_id=11_155_111,
        symbol="ETH",
        type="native",
        contract_address=None,
        decimals=18,
    )
    alice = _user("alice@example.com", 1)
    bob = _user("bob@example.com", 2)
    session.add_all([asset, alice, bob])
    await session.flush()

    source = await ledger.get_or_create_account(
        session,
        asset=asset,
        name="source",
        owner_type="system",
    )
    alice_wallet = await ledger.get_user_wallet_account(session, user=alice, asset=asset)
    await ledger.post(
        session,
        transaction_type=LedgerEntryType.DEPOSIT,
        idempotency_key="fund-alice",
        ref_type="test",
        ref_id="fund-alice",
        legs=[ledger.LedgerLeg(source, asset, -100), ledger.LedgerLeg(alice_wallet, asset, 100)],
    )

    response = await create_transfer(
        session,
        sender=alice,
        to_email="bob@example.com",
        asset_id=asset.id,
        amount=30,
        idempotency_key="transfer-1",
    )

    assert response.status == TransferStatus.CONFIRMED
    transaction = (
        await session.execute(
            select(LedgerTransaction).where(LedgerTransaction.id == response.id),
        )
    ).scalar_one()
    total = (
        await session.execute(
            select(func.sum(LedgerEntry.amount)).where(
                LedgerEntry.transaction_id == transaction.id,
            ),
        )
    ).scalar_one()
    assert int(total) == 0
    assert await ledger.balance(session, user=alice, asset=asset) == (70, 0)
    assert await ledger.balance(session, user=bob, asset=asset) == (30, 0)


async def _fund(session: AsyncSession, user: User, asset: Asset, amount: int) -> None:
    source = await ledger.get_or_create_account(
        session,
        asset=asset,
        name=f"source:{user.id}",
        owner_type="system",
    )
    wallet = await ledger.get_user_wallet_account(session, user=user, asset=asset)
    await ledger.post(
        session,
        transaction_type=LedgerEntryType.DEPOSIT,
        idempotency_key=f"fund:{user.id}:{asset.id}:{amount}",
        ref_type="test",
        ref_id="fund",
        legs=[ledger.LedgerLeg(source, asset, -amount), ledger.LedgerLeg(wallet, asset, amount)],
    )


async def _seed_transfer_world(session: AsyncSession) -> tuple[Asset, User, User]:
    asset = Asset(
        id=uuid.uuid4(),
        chain_id=11_155_111,
        symbol="ETH",
        type="native",
        contract_address=None,
        decimals=18,
    )
    alice = _user("alice-cap@example.com", 1)
    bob = _user("bob-cap@example.com", 2)
    session.add_all([asset, alice, bob])
    await session.flush()
    return asset, alice, bob


@pytest.mark.asyncio
async def test_transfer_accepts_amount_at_asset_cap(session: AsyncSession) -> None:
    asset, alice, bob = await _seed_transfer_world(session)
    await _fund(session, alice, asset, SEPOLIA_ETH_MAX)

    response = await create_transfer(
        session,
        sender=alice,
        to_email=bob.email,
        asset_id=asset.id,
        amount=SEPOLIA_ETH_MAX,
        idempotency_key="transfer-cap-ok",
    )

    assert response.status == TransferStatus.CONFIRMED
    assert await ledger.balance(session, user=alice, asset=asset) == (0, 0)
    assert await ledger.balance(session, user=bob, asset=asset) == (SEPOLIA_ETH_MAX, 0)


@pytest.mark.asyncio
async def test_transfer_rejects_amount_above_asset_cap(session: AsyncSession) -> None:
    asset, alice, bob = await _seed_transfer_world(session)
    await _fund(session, alice, asset, SEPOLIA_ETH_MAX + 1)

    with pytest.raises(HTTPException) as excinfo:
        await create_transfer(
            session,
            sender=alice,
            to_email=bob.email,
            asset_id=asset.id,
            amount=SEPOLIA_ETH_MAX + 1,
            idempotency_key="transfer-cap-too-high",
        )

    assert excinfo.value.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert excinfo.value.detail["code"] == ErrorCode.VALIDATION_ERROR.value  # type: ignore[index]
    assert excinfo.value.detail["message"] == (  # type: ignore[index]
        "Amount exceeds the per-transaction limit of 0.001 ETH"
    )
