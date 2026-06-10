import pytest

pytest.importorskip("aiosqlite")

from http import HTTPStatus

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import DepositStatus, ErrorCode
from app.models.tables import LedgerTransaction, OnchainDeposit
from app.services import ledger
from app.services.wallet_service import deposit_confirmations, request_faucet
from tests.support import FakeChainClient, seed_asset, seed_deposit_address, seed_user

CHAIN_ID = 11_155_111
ALICE_ADDR = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
FAUCET_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
SEPOLIA_ETH_MAX = 1_000_000_000_000_000
CONFIRMED_BLOCK = 100
CURRENT_BLOCK = 112
CONFIRMATION_DEPTH = 12


@pytest.mark.asyncio
async def test_faucet_simulation_credits_immediately(session: AsyncSession) -> None:
    asset = await seed_asset(
        session, chain_id=CHAIN_ID, asset_type="native", symbol="ETH", decimals=18,
    )
    user = await seed_user(session, email="alice@example.com", hd_index=1)
    await seed_deposit_address(session, user=user, address=ALICE_ADDR)

    response = await request_faucet(
        session,
        user=user,
        asset_id=asset.id,
        amount=SEPOLIA_ETH_MAX,
        idempotency_key="faucet-1",
    )
    assert response.status == DepositStatus.CREDITED
    assert await ledger.available_balance(session, user=user, asset=asset) == SEPOLIA_ETH_MAX

    deposit = (await session.execute(select(OnchainDeposit))).scalar_one()
    assert deposit.status == DepositStatus.CREDITED.value
    assert deposit.to_address == ALICE_ADDR

    # Replaying the same idempotency key neither double-credits nor duplicates the deposit.
    replay = await request_faucet(
        session,
        user=user,
        asset_id=asset.id,
        amount=SEPOLIA_ETH_MAX,
        idempotency_key="faucet-1",
    )
    assert replay.tx_hash == response.tx_hash
    assert await ledger.available_balance(session, user=user, asset=asset) == SEPOLIA_ETH_MAX
    deposit_count = (await session.execute(select(func.count(OnchainDeposit.id)))).scalar_one()
    assert deposit_count == 1


@pytest.mark.asyncio
async def test_faucet_real_send_broadcasts_and_returns_seen(session: AsyncSession) -> None:
    asset = await seed_asset(
        session, chain_id=CHAIN_ID, asset_type="native", symbol="ETH", decimals=18,
    )
    user = await seed_user(session, email="alice@example.com", hd_index=1)
    await seed_deposit_address(session, user=user, address=ALICE_ADDR)

    sender = FakeChainClient(chain_id=CHAIN_ID)
    response = await request_faucet(
        session,
        user=user,
        asset_id=asset.id,
        amount=SEPOLIA_ETH_MAX,
        idempotency_key="faucet-2",
        faucet_private_key=FAUCET_KEY,
        sender_factory=lambda _chain_id: sender,
    )

    assert response.status == DepositStatus.SEEN
    assert len(sender.sent) == 1
    assert sender.sent[0].kind == "native"
    assert sender.sent[0].to_address == ALICE_ADDR
    assert sender.sent[0].value == SEPOLIA_ETH_MAX
    # Real mode defers crediting to the watcher (no OnchainDeposit here) but writes a single
    # idempotency marker keyed by the idempotency key so retries don't re-broadcast.
    assert (await session.execute(select(func.count(OnchainDeposit.id)))).scalar_one() == 0
    assert (await session.execute(select(func.count(LedgerTransaction.id)))).scalar_one() == 1


@pytest.mark.asyncio
async def test_faucet_real_send_is_idempotent_on_retry(session: AsyncSession) -> None:
    asset = await seed_asset(
        session, chain_id=CHAIN_ID, asset_type="native", symbol="ETH", decimals=18,
    )
    user = await seed_user(session, email="alice@example.com", hd_index=1)
    await seed_deposit_address(session, user=user, address=ALICE_ADDR)
    sender = FakeChainClient(chain_id=CHAIN_ID)

    async def claim() -> str:
        result = await request_faucet(
            session,
            user=user,
            asset_id=asset.id,
            amount=SEPOLIA_ETH_MAX,
            idempotency_key="faucet-retry",
            faucet_private_key=FAUCET_KEY,
            sender_factory=lambda _chain_id: sender,
        )
        return result.tx_hash

    first = await claim()
    second = await claim()  # client retried the POST with the same Idempotency-Key
    assert first == second
    # The funding tx is broadcast exactly once despite the retry.
    assert len(sender.sent) == 1


@pytest.mark.asyncio
async def test_faucet_rejects_amount_above_asset_cap(session: AsyncSession) -> None:
    asset = await seed_asset(
        session, chain_id=CHAIN_ID, asset_type="native", symbol="ETH", decimals=18,
    )
    user = await seed_user(session, email="alice@example.com", hd_index=1)
    await seed_deposit_address(session, user=user, address=ALICE_ADDR)

    with pytest.raises(HTTPException) as excinfo:
        await request_faucet(
            session,
            user=user,
            asset_id=asset.id,
            amount=SEPOLIA_ETH_MAX + 1,
            idempotency_key="faucet-over-cap",
        )

    assert excinfo.value.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert excinfo.value.detail["code"] == ErrorCode.VALIDATION_ERROR.value  # type: ignore[index]
    assert excinfo.value.detail["message"] == (  # type: ignore[index]
        "Amount exceeds the per-transaction limit of 0.001 ETH"
    )


def test_deposit_confirmations_match_credit_threshold_depth() -> None:
    credited = OnchainDeposit(block_number=CONFIRMED_BLOCK)
    # Watcher credits at head - block_number >= confirmations; the display must use the same depth.
    assert deposit_confirmations(credited, CURRENT_BLOCK) == CONFIRMATION_DEPTH
    assert deposit_confirmations(credited, None) == 0
    simulated = OnchainDeposit(block_number=0)
    assert deposit_confirmations(simulated, CURRENT_BLOCK) == 0
