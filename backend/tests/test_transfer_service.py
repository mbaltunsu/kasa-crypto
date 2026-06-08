from collections.abc import AsyncIterator
import uuid

import pytest

pytest.importorskip("aiosqlite")
pytest.importorskip("pytest_asyncio")
pytest.importorskip("sqlalchemy")

import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.enums import LedgerEntryType, TransferStatus, UserRole
from app.db import Base
from app.models.tables import Asset, LedgerEntry, LedgerTransaction, User
from app.services import ledger
from app.services.transfer_service import create_transfer


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
    alice = User(email="alice@example.com", password_hash="hash", role=UserRole.USER.value, hd_index=1)
    bob = User(email="bob@example.com", password_hash="hash", role=UserRole.USER.value, hd_index=2)
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
            select(func.sum(LedgerEntry.amount)).where(LedgerEntry.transaction_id == transaction.id),
        )
    ).scalar_one()
    assert int(total) == 0
    assert await ledger.balance(session, user=alice, asset=asset) == (70, 0)
    assert await ledger.balance(session, user=bob, asset=asset) == (30, 0)
