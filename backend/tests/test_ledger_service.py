from collections.abc import AsyncIterator
import uuid

import pytest

pytest.importorskip("aiosqlite")
pytest.importorskip("pytest_asyncio")
pytest.importorskip("sqlalchemy")

import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.enums import DepositStatus, LedgerEntryType, UserRole
from app.db import Base
from app.models.tables import Asset, LedgerEntry, OnchainDeposit, User
from app.services import ledger


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


async def _asset(session: AsyncSession) -> Asset:
    asset = Asset(
        id=uuid.uuid4(),
        chain_id=11_155_111,
        symbol="ETH",
        type="native",
        contract_address=None,
        decimals=18,
    )
    session.add(asset)
    await session.flush()
    return asset


async def _user(session: AsyncSession, email: str) -> User:
    user = User(
        email=email,
        password_hash="hash",
        role=UserRole.USER.value,
        hd_index=1,
    )
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_ledger_sum_zero_invariant_and_idempotency(session: AsyncSession) -> None:
    asset = await _asset(session)
    source = await ledger.get_or_create_account(
        session,
        asset=asset,
        name="source",
        owner_type="system",
    )
    sink = await ledger.get_or_create_account(
        session,
        asset=asset,
        name="sink",
        owner_type="system",
    )

    with pytest.raises(ledger.LedgerInvariantError):
        await ledger.post(
            session,
            transaction_type=LedgerEntryType.ADJUSTMENT,
            idempotency_key="bad",
            ref_type="test",
            ref_id="bad",
            legs=[ledger.LedgerLeg(source, asset, -10), ledger.LedgerLeg(sink, asset, 9)],
        )

    tx = await ledger.post(
        session,
        transaction_type=LedgerEntryType.ADJUSTMENT,
        idempotency_key="good",
        ref_type="test",
        ref_id="good",
        legs=[ledger.LedgerLeg(source, asset, -10), ledger.LedgerLeg(sink, asset, 10)],
    )
    replay = await ledger.post(
        session,
        transaction_type=LedgerEntryType.ADJUSTMENT,
        idempotency_key="good",
        ref_type="test",
        ref_id="good",
        legs=[ledger.LedgerLeg(source, asset, -99), ledger.LedgerLeg(sink, asset, 99)],
    )

    assert replay.id == tx.id
    count = (
        await session.execute(
            select(func.count(LedgerEntry.id)).where(LedgerEntry.transaction_id == tx.id),
        )
    ).scalar_one()
    assert count == 2


@pytest.mark.asyncio
async def test_get_or_create_account_tolerates_duplicate_system_accounts(session: AsyncSession) -> None:
    """#10: nullable user_id means Postgres allows duplicate `system` accounts. get_or_create must
    not crash with MultipleResultsFound when duplicates already exist — it returns an existing row."""
    from app.models.tables import LedgerAccount

    asset = await _asset(session)
    dup1 = LedgerAccount(owner_type="system", user_id=None, asset_id=asset.id, name="reserve")
    dup2 = LedgerAccount(owner_type="system", user_id=None, asset_id=asset.id, name="reserve")
    session.add_all([dup1, dup2])
    await session.flush()

    account = await ledger.get_or_create_account(session, asset=asset, name="reserve", owner_type="system")
    assert account.id in {dup1.id, dup2.id}


@pytest.mark.asyncio
async def test_ledger_available_and_pending_balance(session: AsyncSession) -> None:
    asset = await _asset(session)
    user = await _user(session, "alice@example.com")
    system = await ledger.get_or_create_account(
        session,
        asset=asset,
        name="source",
        owner_type="system",
    )
    wallet = await ledger.get_user_wallet_account(session, user=user, asset=asset)
    await ledger.post(
        session,
        transaction_type=LedgerEntryType.DEPOSIT,
        idempotency_key="credit",
        ref_type="test",
        ref_id="credit",
        legs=[ledger.LedgerLeg(system, asset, -100), ledger.LedgerLeg(wallet, asset, 100)],
    )
    session.add(
        OnchainDeposit(
            chain_id=asset.chain_id,
            tx_hash="0x" + ("1" * 64),
            log_index=0,
            block_number=1,
            block_hash="0x" + ("2" * 64),
            to_address="0x0000000000000000000000000000000000000000",
            asset_id=asset.id,
            amount=50,
            status=DepositStatus.SEEN.value,
            user_id=user.id,
        ),
    )
    await session.flush()

    assert await ledger.balance(session, user=user, asset=asset) == (100, 50)
