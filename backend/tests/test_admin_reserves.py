import pytest

pytest.importorskip("aiosqlite")

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import LedgerEntryType
from app.models.tables import Asset, User
from app.schemas.admin import ReserveAssetResponse, ReservesResponse
from app.services import admin_service, ledger
from tests.support import FakeChainClient, seed_asset, seed_deposit_address, seed_user

CHAIN_ID = 11_155_111
ALICE_ADDR = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
HOT_ADDR = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
TOKEN = "0x5FbDB2315678afecb367f032d93F642f64180aa3"
ONE_ETH = 1_000_000_000_000_000_000


async def _credit_wallet(session: AsyncSession, user: User, asset: Asset, amount: int) -> None:
    source = await ledger.get_or_create_account(
        session, asset=asset, name="ext_source", owner_type="system",
    )
    wallet = await ledger.get_user_wallet_account(session, user=user, asset=asset)
    await ledger.post(
        session,
        transaction_type=LedgerEntryType.DEPOSIT,
        idempotency_key=f"credit:{user.id}:{asset.id}",
        ref_type="test",
        ref_id="credit",
        legs=[ledger.LedgerLeg(source, asset, -amount), ledger.LedgerLeg(wallet, asset, amount)],
    )


def _row(report: ReservesResponse, asset_id: UUID) -> ReserveAssetResponse:
    return next(row for row in report.assets if row.asset_id == asset_id)


@pytest.mark.asyncio
async def test_reserves_fall_back_to_liabilities_without_factory(session: AsyncSession) -> None:
    asset = await seed_asset(session, chain_id=CHAIN_ID, asset_type="native", symbol="ETH", decimals=18)
    user = await seed_user(session, email="a@example.com", hd_index=1)
    await _credit_wallet(session, user, asset, ONE_ETH)

    report = await admin_service.reserves(session)
    row = _row(report, asset.id)
    assert row.liabilities == ONE_ETH
    assert row.reserves == ONE_ETH
    assert row.delta == 0


@pytest.mark.asyncio
async def test_reserves_sum_onchain_native_balances(session: AsyncSession) -> None:
    asset = await seed_asset(session, chain_id=CHAIN_ID, asset_type="native", symbol="ETH", decimals=18)
    user = await seed_user(session, email="a@example.com", hd_index=1)
    await seed_deposit_address(session, user=user, address=ALICE_ADDR)
    await _credit_wallet(session, user, asset, ONE_ETH)

    # Deposit address holds the full liability; the hot wallet carries a 0.25 ETH surplus.
    client = FakeChainClient(
        chain_id=CHAIN_ID,
        native_balances={ALICE_ADDR.lower(): ONE_ETH, HOT_ADDR.lower(): ONE_ETH // 4},
    )
    report = await admin_service.reserves(
        session, hot_wallet_address=HOT_ADDR, balance_factory=lambda _chain_id: client,
    )
    row = _row(report, asset.id)
    assert row.liabilities == ONE_ETH
    assert row.reserves == ONE_ETH + ONE_ETH // 4
    assert row.delta == ONE_ETH // 4


@pytest.mark.asyncio
async def test_reserves_sum_onchain_erc20_balances(session: AsyncSession) -> None:
    asset = await seed_asset(
        session,
        chain_id=CHAIN_ID,
        asset_type="erc20",
        symbol="DEMO",
        decimals=18,
        contract_address=TOKEN,
    )
    user = await seed_user(session, email="a@example.com", hd_index=1)
    await seed_deposit_address(session, user=user, address=ALICE_ADDR)
    await _credit_wallet(session, user, asset, ONE_ETH)

    client = FakeChainClient(
        chain_id=CHAIN_ID,
        erc20_balances={(TOKEN.lower(), ALICE_ADDR.lower()): ONE_ETH},
    )
    report = await admin_service.reserves(
        session, hot_wallet_address=HOT_ADDR, balance_factory=lambda _chain_id: client,
    )
    row = _row(report, asset.id)
    assert row.reserves == ONE_ETH
    assert row.delta == 0
