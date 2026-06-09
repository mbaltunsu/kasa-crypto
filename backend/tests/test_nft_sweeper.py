import pytest

pytest.importorskip("aiosqlite")

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chain.types import TxReceipt
from app.core.config import get_settings
from app.core.enums import NftDepositStatus, NftHoldingStatus, NftSweepStatus
from app.core.hd_wallet import derive_account
from app.models.tables import HotWalletNonce, NftDeposit, NftHolding, NftSweep
from tests.support import FakeChainClient, seed_deposit_address, seed_user
from worker import nft_sweeper

CHAIN_ID = 11_155_111
HOT_ADDR = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
HOT_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
DEPOSIT_ADDR = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
SENDER_ADDR = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC"
CONTRACT = "0x88F67A2EbD4C342496d0A477EF58F3a89BCF95F2"
TOKEN_ID = "42"  # noqa: S105
FIRST_NONCE = 7
DEPOSIT_NONCE = 3
FIRST_UNMINED_HEAD = 30
DROPPED_UNMINED_HEAD = 50


async def _credited_deposit(
    session: AsyncSession,
    *,
    token_id: str = TOKEN_ID,
    hd_index: int = 1,
    address: str = DEPOSIT_ADDR,
) -> tuple[NftDeposit, NftHolding]:
    user = await seed_user(session, email=f"user-{token_id}@example.com", hd_index=hd_index)
    await seed_deposit_address(session, user=user, address=address)
    deposit = NftDeposit(
        user_id=user.id,
        chain_id=CHAIN_ID,
        contract=CONTRACT,
        token_id=token_id,
        from_address=SENDER_ADDR,
        to_address=address,
        tx_hash="0x" + f"{int(token_id):064x}",
        log_index=int(token_id),
        block_number=10,
        block_hash="0x" + "aa" * 32,
        status=NftDepositStatus.CREDITED.value,
    )
    holding = NftHolding(
        user_id=user.id,
        chain_id=CHAIN_ID,
        contract=CONTRACT,
        token_id=token_id,
        status=NftHoldingStatus.HELD.value,
    )
    session.add_all([deposit, holding])
    await session.flush()
    return deposit, holding


async def _sweep(
    session: AsyncSession,
    *,
    status: NftSweepStatus,
    token_id: str = TOKEN_ID,
    hd_index: int = 1,
) -> NftSweep:
    deposit, _holding = await _credited_deposit(session, token_id=token_id, hd_index=hd_index)
    sweep = NftSweep(
        chain_id=CHAIN_ID,
        contract=CONTRACT,
        token_id=token_id,
        deposit_address=deposit.to_address,
        hd_index=hd_index,
        nft_deposit_id=deposit.id,
        status=status.value,
    )
    session.add(sweep)
    await session.flush()
    return sweep


async def _only_sweep(session: AsyncSession) -> NftSweep:
    return (await session.execute(select(NftSweep))).scalar_one()


@pytest.mark.asyncio
async def test_discover_creates_pending_sweep_idempotently(session: AsyncSession) -> None:
    deposit, _holding = await _credited_deposit(session)
    client = FakeChainClient(chain_id=CHAIN_ID)

    created = await nft_sweeper.discover_sweeps(session, client)
    second = await nft_sweeper.discover_sweeps(session, client)

    assert created == 1
    assert second == 0
    sweep = await _only_sweep(session)
    assert sweep.status == NftSweepStatus.PENDING.value
    assert sweep.nft_deposit_id == deposit.id
    assert sweep.deposit_address == DEPOSIT_ADDR
    assert sweep.hd_index == 1


@pytest.mark.asyncio
async def test_discover_rearms_failed_sweep_under_attempt_cap(session: AsyncSession) -> None:
    sweep = await _sweep(session, status=NftSweepStatus.FAILED)
    sweep.attempts = 2
    sweep.gas_fund_tx_hash = "0xgas"
    sweep.gas_fund_nonce = 7
    sweep.sweep_signed_tx = "0xsigned"
    sweep.sweep_tx_hash = "0xsweep"
    sweep.sweep_nonce = 3
    sweep.unmined_since_block = 42
    sweep.error = "old failure"
    client = FakeChainClient(chain_id=CHAIN_ID)

    rearmed = await nft_sweeper.discover_sweeps(session, client)

    assert rearmed == 1
    await session.refresh(sweep)
    assert sweep.status == NftSweepStatus.PENDING.value
    assert sweep.attempts == nft_sweeper.MAX_SWEEP_ATTEMPTS - 1
    # re-arm clears all tx/marker fields (list[object] avoids stale per-field narrowing from the
    # non-None assignments above tripping mypy's unreachable / strict-equality checks).
    cleared: list[object] = [
        sweep.gas_fund_tx_hash,
        sweep.gas_fund_nonce,
        sweep.sweep_signed_tx,
        sweep.sweep_tx_hash,
        sweep.sweep_nonce,
        sweep.unmined_since_block,
        sweep.error,
    ]
    assert all(v is None for v in cleared)


@pytest.mark.asyncio
async def test_discover_leaves_failed_sweep_at_attempt_cap(session: AsyncSession) -> None:
    sweep = await _sweep(session, status=NftSweepStatus.FAILED)
    sweep.attempts = 3
    sweep.error = "needs manual intervention"
    client = FakeChainClient(chain_id=CHAIN_ID)

    rearmed = await nft_sweeper.discover_sweeps(session, client)

    assert rearmed == 0
    await session.refresh(sweep)
    assert sweep.status == NftSweepStatus.FAILED.value
    assert sweep.attempts == nft_sweeper.MAX_SWEEP_ATTEMPTS
    assert sweep.error == "needs manual intervention"


@pytest.mark.asyncio
async def test_fund_pending_signs_broadcasts_and_marks_funded(session: AsyncSession) -> None:
    sweep = await _sweep(session, status=NftSweepStatus.PENDING)
    client = FakeChainClient(chain_id=CHAIN_ID, nonces={HOT_ADDR.lower(): FIRST_NONCE})

    progressed = await nft_sweeper.fund_pending(
        session,
        client,
        hot_wallet_key=HOT_KEY,
        hot_wallet_address=HOT_ADDR,
    )

    assert progressed == 1
    await session.refresh(sweep)
    assert sweep.status == NftSweepStatus.FUNDING.value
    assert sweep.gas_fund_nonce == FIRST_NONCE
    assert sweep.gas_fund_tx_hash is not None
    assert client.sent[0].kind == "native"
    assert client.sent[0].to_address == DEPOSIT_ADDR
    assert client.sent[0].value == nft_sweeper.GAS_BUDGET_WEI
    nonce = (
        await session.execute(select(HotWalletNonce).where(HotWalletNonce.chain_id == CHAIN_ID))
    ).scalar_one()
    assert nonce.next_nonce == FIRST_NONCE + 1

    client.native_balances[DEPOSIT_ADDR.lower()] = nft_sweeper.GAS_BUDGET_WEI
    progressed = await nft_sweeper.fund_pending(
        session,
        client,
        hot_wallet_key=HOT_KEY,
        hot_wallet_address=HOT_ADDR,
    )

    assert progressed == 1
    await session.refresh(sweep)
    assert sweep.status == NftSweepStatus.FUNDED.value


@pytest.mark.asyncio
async def test_fund_pending_already_funded_skips_tx(session: AsyncSession) -> None:
    sweep = await _sweep(session, status=NftSweepStatus.PENDING)
    client = FakeChainClient(
        chain_id=CHAIN_ID,
        native_balances={DEPOSIT_ADDR.lower(): nft_sweeper.GAS_BUDGET_WEI},
    )

    progressed = await nft_sweeper.fund_pending(
        session,
        client,
        hot_wallet_key=HOT_KEY,
        hot_wallet_address=HOT_ADDR,
    )

    assert progressed == 1
    await session.refresh(sweep)
    assert sweep.status == NftSweepStatus.FUNDED.value
    assert sweep.gas_fund_tx_hash is None
    assert client.sent == []


@pytest.mark.asyncio
async def test_funding_sweep_rebroadcasts_gas_at_persisted_nonce(
    session: AsyncSession,
) -> None:
    sweep = await _sweep(session, status=NftSweepStatus.FUNDING)
    sweep.gas_fund_nonce = FIRST_NONCE
    sweep.gas_fund_tx_hash = "0xold"
    client = FakeChainClient(chain_id=CHAIN_ID, nonces={HOT_ADDR.lower(): FIRST_NONCE + 99})

    progressed = await nft_sweeper.fund_pending(
        session,
        client,
        hot_wallet_key=HOT_KEY,
        hot_wallet_address=HOT_ADDR,
    )

    assert progressed == 1
    await session.refresh(sweep)
    assert sweep.status == NftSweepStatus.FUNDING.value
    assert sweep.gas_fund_nonce == FIRST_NONCE
    assert client.sent[0].kind == "native"
    assert client.sent[0].nonce == FIRST_NONCE
    nonce_rows = (
        await session.execute(select(HotWalletNonce).where(HotWalletNonce.chain_id == CHAIN_ID))
    ).scalars().all()
    assert nonce_rows == []


@pytest.mark.asyncio
async def test_sweep_funded_signs_from_deposit_address(session: AsyncSession) -> None:
    sweep = await _sweep(session, status=NftSweepStatus.FUNDED, hd_index=2)
    client = FakeChainClient(chain_id=CHAIN_ID, nonces={DEPOSIT_ADDR.lower(): DEPOSIT_NONCE})

    broadcast = await nft_sweeper.sweep_funded(session, client, hot_wallet_address=HOT_ADDR)

    assert broadcast == 1
    await session.refresh(sweep)
    account = derive_account(get_settings().master_mnemonic, chain_id=CHAIN_ID, hd_index=2)
    assert sweep.status == NftSweepStatus.SWEEPING.value
    assert sweep.sweep_nonce == DEPOSIT_NONCE
    assert sweep.sweep_signed_tx is not None
    assert client.sent[0].kind == "erc721_transfer"
    assert client.sent[0].from_address == DEPOSIT_ADDR
    assert client.sent[0].to_address == HOT_ADDR
    assert client.sent[0].private_key == account.private_key
    assert client.sent[0].nonce == DEPOSIT_NONCE


@pytest.mark.asyncio
async def test_confirm_happy_path_marks_swept_and_keeps_holding_held(
    session: AsyncSession,
) -> None:
    sweep = await _sweep(session, status=NftSweepStatus.SWEEPING)
    sweep.sweep_tx_hash = "0xsweep"
    sweep.sweep_nonce = DEPOSIT_NONCE
    holding = (await session.execute(select(NftHolding))).scalar_one()
    block_hash = "0x" + "ab" * 32
    client = FakeChainClient(
        chain_id=CHAIN_ID,
        head=20,
        block_hashes={10: block_hash},
        receipts={
            "0xsweep": TxReceipt(
                tx_hash="0xsweep",
                status=1,
                block_number=10,
                block_hash=block_hash,
            ),
        },
        erc721_owners={(CONTRACT.lower(), TOKEN_ID): HOT_ADDR},
    )

    confirmed = await nft_sweeper.confirm_sweeps(
        session,
        client,
        confirmations=5,
        hot_wallet_address=HOT_ADDR,
    )

    assert confirmed == 1
    await session.refresh(sweep)
    await session.refresh(holding)
    assert sweep.status == NftSweepStatus.SWEPT.value
    assert holding.status == NftHoldingStatus.HELD.value


@pytest.mark.asyncio
async def test_confirm_does_not_mark_swept_when_owner_is_not_hot_wallet(
    session: AsyncSession,
) -> None:
    sweep = await _sweep(session, status=NftSweepStatus.SWEEPING)
    sweep.sweep_tx_hash = "0xsweep"
    sweep.sweep_nonce = DEPOSIT_NONCE
    block_hash = "0x" + "ab" * 32
    client = FakeChainClient(
        chain_id=CHAIN_ID,
        head=20,
        block_hashes={10: block_hash},
        receipts={
            "0xsweep": TxReceipt(
                tx_hash="0xsweep",
                status=1,
                block_number=10,
                block_hash=block_hash,
            ),
        },
        erc721_owners={(CONTRACT.lower(), TOKEN_ID): SENDER_ADDR},
    )

    confirmed = await nft_sweeper.confirm_sweeps(
        session,
        client,
        confirmations=5,
        hot_wallet_address=HOT_ADDR,
    )

    assert confirmed == 0
    await session.refresh(sweep)
    assert sweep.status == NftSweepStatus.SWEEPING.value


@pytest.mark.asyncio
async def test_confirm_grace_gate_waits_for_receipt_then_sweeps(session: AsyncSession) -> None:
    sweep = await _sweep(session, status=NftSweepStatus.SWEEPING)
    sweep.sweep_tx_hash = "0xsweep"
    sweep.sweep_nonce = DEPOSIT_NONCE
    client = FakeChainClient(
        chain_id=CHAIN_ID,
        head=FIRST_UNMINED_HEAD,
        latest_nonces={DEPOSIT_ADDR.lower(): DEPOSIT_NONCE + 1},
    )

    confirmed = await nft_sweeper.confirm_sweeps(
        session,
        client,
        confirmations=5,
        hot_wallet_address=HOT_ADDR,
    )

    assert confirmed == 0
    await session.refresh(sweep)
    assert sweep.status == NftSweepStatus.SWEEPING.value
    marker: int | None = sweep.unmined_since_block
    assert marker == FIRST_UNMINED_HEAD

    block_hash = "0x" + "ab" * 32
    client.receipts["0xsweep"] = TxReceipt(
        tx_hash="0xsweep",
        status=1,
        block_number=31,
        block_hash=block_hash,
    )
    client.block_hashes[31] = block_hash
    client.erc721_owners[(CONTRACT.lower(), TOKEN_ID)] = HOT_ADDR
    client.head = 40

    confirmed = await nft_sweeper.confirm_sweeps(
        session,
        client,
        confirmations=5,
        hot_wallet_address=HOT_ADDR,
    )

    assert confirmed == 1
    await session.refresh(sweep)
    assert sweep.status == NftSweepStatus.SWEPT.value
    cleared_marker: int | None = sweep.unmined_since_block
    assert cleared_marker is None


@pytest.mark.asyncio
async def test_confirm_grace_gate_fails_persisted_absent_tx(session: AsyncSession) -> None:
    sweep = await _sweep(session, status=NftSweepStatus.SWEEPING)
    sweep.sweep_tx_hash = "0xdropped"
    sweep.sweep_nonce = DEPOSIT_NONCE
    client = FakeChainClient(
        chain_id=CHAIN_ID,
        head=DROPPED_UNMINED_HEAD,
        latest_nonces={DEPOSIT_ADDR.lower(): DEPOSIT_NONCE + 1},
    )

    confirmed = await nft_sweeper.confirm_sweeps(
        session,
        client,
        confirmations=6,
        hot_wallet_address=HOT_ADDR,
    )

    assert confirmed == 0
    await session.refresh(sweep)
    marker: int | None = sweep.unmined_since_block
    assert marker == DROPPED_UNMINED_HEAD

    client.head = DROPPED_UNMINED_HEAD + 6
    confirmed = await nft_sweeper.confirm_sweeps(
        session,
        client,
        confirmations=6,
        hot_wallet_address=HOT_ADDR,
    )

    assert confirmed == 0
    await session.refresh(sweep)
    assert sweep.status == NftSweepStatus.FAILED.value
    assert sweep.error == "sweep tx dropped (nonce superseded)"
