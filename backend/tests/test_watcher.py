import pytest

pytest.importorskip("aiosqlite")

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chain.types import Erc20Transfer, NativeTransfer
from app.core.enums import DepositStatus, LedgerEntryType
from app.models.tables import Asset, OnchainDeposit, User
from app.services import ledger
from tests.support import (
    FakeChainClient,
    seed_asset,
    seed_deposit_address,
    seed_user,
)
from worker import watcher

CHAIN_ID = 11_155_111
ALICE_ADDR = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
TOKEN = "0x5FbDB2315678afecb367f032d93F642f64180aa3"
SENDER = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
ONE_ETH = 1_000_000_000_000_000_000


async def _world(session: AsyncSession) -> tuple[Asset, Asset, User]:
    native = await seed_asset(
        session, chain_id=CHAIN_ID, asset_type="native", symbol="ETH", decimals=18,
    )
    token = await seed_asset(
        session,
        chain_id=CHAIN_ID,
        asset_type="erc20",
        symbol="DEMO",
        decimals=18,
        contract_address=TOKEN,
    )
    alice = await seed_user(session, email="alice@example.com", hd_index=1)
    await seed_deposit_address(session, user=alice, address=ALICE_ADDR)
    return native, token, alice


async def _deposit_count(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count(OnchainDeposit.id)))).scalar_one())


@pytest.mark.asyncio
async def test_record_deposits_inserts_seen_erc20_and_is_idempotent(session: AsyncSession) -> None:
    _native, token, alice = await _world(session)
    client = FakeChainClient(
        chain_id=CHAIN_ID,
        head=200,
        erc20_transfers=[
            Erc20Transfer(
                token_address=TOKEN,
                from_address=SENDER,
                to_address=ALICE_ADDR,
                value=ONE_ETH,
                tx_hash="0x" + "11" * 32,
                log_index=3,
                block_number=100,
                block_hash="0x" + "aa" * 32,
            ),
        ],
    )

    inserted = await watcher.record_deposits(session, client, from_block=1, to_block=200)
    assert inserted == 1

    deposit = (await session.execute(select(OnchainDeposit))).scalar_one()
    assert deposit.status == DepositStatus.SEEN.value
    assert deposit.user_id == alice.id
    assert deposit.asset_id == token.id
    assert int(deposit.amount) == ONE_ETH
    assert deposit.log_index == 3

    # Re-scanning the same range must not duplicate the deposit.
    again = await watcher.record_deposits(session, client, from_block=1, to_block=200)
    assert again == 0
    assert await _deposit_count(session) == 1


@pytest.mark.asyncio
async def test_record_deposits_records_native_transfer(session: AsyncSession) -> None:
    native, _token, alice = await _world(session)
    client = FakeChainClient(
        chain_id=CHAIN_ID,
        head=200,
        native_transfers=[
            NativeTransfer(
                to_address=ALICE_ADDR,
                value=2 * ONE_ETH,
                tx_hash="0x" + "22" * 32,
                block_number=101,
                block_hash="0x" + "bb" * 32,
            ),
        ],
    )

    inserted = await watcher.record_deposits(session, client, from_block=1, to_block=200)
    assert inserted == 1

    deposit = (await session.execute(select(OnchainDeposit))).scalar_one()
    assert deposit.asset_id == native.id
    assert deposit.user_id == alice.id
    assert deposit.log_index == watcher.NATIVE_LOG_INDEX
    assert int(deposit.amount) == 2 * ONE_ETH

    again = await watcher.record_deposits(session, client, from_block=1, to_block=200)
    assert again == 0


@pytest.mark.asyncio
async def test_record_deposits_records_internal_transfers_when_enabled(session: AsyncSession) -> None:
    """#11: with internal-transfer watching on, native value delivered via a contract internal call
    (carried in fetch_internal_transfers) is recorded like any other deposit."""
    native, _token, alice = await _world(session)
    client = FakeChainClient(
        chain_id=CHAIN_ID,
        head=200,
        internal_transfers=[
            NativeTransfer(
                to_address=ALICE_ADDR,
                value=3 * ONE_ETH,
                tx_hash="0x" + "44" * 32,
                block_number=100,
                block_hash="0x" + "dd" * 32,
                log_index=-2,
            ),
        ],
    )
    inserted = await watcher.record_deposits(
        session, client, from_block=1, to_block=200, watch_internal=True,
    )
    assert inserted == 1
    deposit = (await session.execute(select(OnchainDeposit))).scalar_one()
    assert deposit.asset_id == native.id
    assert deposit.user_id == alice.id
    assert int(deposit.amount) == 3 * ONE_ETH
    assert deposit.log_index == -2


@pytest.mark.asyncio
async def test_record_deposits_ignores_internal_transfers_when_disabled(session: AsyncSession) -> None:
    await _world(session)
    client = FakeChainClient(
        chain_id=CHAIN_ID,
        head=200,
        internal_transfers=[
            NativeTransfer(
                to_address=ALICE_ADDR,
                value=ONE_ETH,
                tx_hash="0x" + "44" * 32,
                block_number=100,
                block_hash="0x" + "dd" * 32,
                log_index=-2,
            ),
        ],
    )
    # Default (flag off): internal transfers are not scanned, so nothing is recorded.
    inserted = await watcher.record_deposits(session, client, from_block=1, to_block=200)
    assert inserted == 0
    assert await _deposit_count(session) == 0


@pytest.mark.asyncio
async def test_internal_and_top_level_native_in_one_tx_are_both_recorded(session: AsyncSession) -> None:
    """A top-level native send (log_index -1) and an internal transfer (log_index -2) in the SAME tx
    must both record without colliding on the (chain, tx, log_index) dedup key."""
    _native, _token, alice = await _world(session)
    tx_hash = "0x" + "55" * 32
    block_hash = "0x" + "ee" * 32
    client = FakeChainClient(
        chain_id=CHAIN_ID,
        head=200,
        native_transfers=[
            NativeTransfer(
                to_address=ALICE_ADDR, value=ONE_ETH, tx_hash=tx_hash, block_number=100, block_hash=block_hash,
            ),
        ],
        internal_transfers=[
            NativeTransfer(
                to_address=ALICE_ADDR,
                value=2 * ONE_ETH,
                tx_hash=tx_hash,
                block_number=100,
                block_hash=block_hash,
                log_index=-2,
            ),
        ],
    )
    inserted = await watcher.record_deposits(
        session, client, from_block=1, to_block=200, watch_internal=True,
    )
    assert inserted == 2
    assert await _deposit_count(session) == 2


@pytest.mark.asyncio
async def test_record_deposits_ignores_unknown_recipient(session: AsyncSession) -> None:
    await _world(session)
    client = FakeChainClient(
        chain_id=CHAIN_ID,
        head=200,
        native_transfers=[
            NativeTransfer(
                to_address="0x000000000000000000000000000000000000dEaD",
                value=ONE_ETH,
                tx_hash="0x" + "33" * 32,
                block_number=100,
                block_hash="0x" + "cc" * 32,
            ),
        ],
    )

    inserted = await watcher.record_deposits(session, client, from_block=1, to_block=200)
    assert inserted == 0
    assert await _deposit_count(session) == 0


@pytest.mark.asyncio
async def test_confirm_and_credit_credits_after_confirmations(session: AsyncSession) -> None:
    _native, token, alice = await _world(session)
    # Credit re-validates the recorded block hash against the canonical chain.
    client = FakeChainClient(chain_id=CHAIN_ID, head=110, block_hashes={100: "0x" + "aa" * 32})
    session.add(
        OnchainDeposit(
            chain_id=CHAIN_ID,
            tx_hash="0x" + "11" * 32,
            log_index=0,
            block_number=100,
            block_hash="0x" + "aa" * 32,
            to_address=ALICE_ADDR,
            asset_id=token.id,
            amount=ONE_ETH,
            status=DepositStatus.SEEN.value,
            user_id=alice.id,
        ),
    )
    await session.flush()

    credited = await watcher.confirm_and_credit(session, client, confirmations=5)
    assert credited == 1

    deposit = (await session.execute(select(OnchainDeposit))).scalar_one()
    assert deposit.status == DepositStatus.CREDITED.value
    available, pending = await ledger.balance(session, user=alice, asset=token)
    assert available == ONE_ETH
    assert pending == 0

    # Idempotent: a second pass neither re-credits nor double-counts.
    assert await watcher.confirm_and_credit(session, client, confirmations=5) == 0
    available_again, _ = await ledger.balance(session, user=alice, asset=token)
    assert available_again == ONE_ETH


@pytest.mark.asyncio
async def test_confirm_and_credit_waits_for_confirmations(session: AsyncSession) -> None:
    _native, token, alice = await _world(session)
    client = FakeChainClient(chain_id=CHAIN_ID, head=110)
    session.add(
        OnchainDeposit(
            chain_id=CHAIN_ID,
            tx_hash="0x" + "11" * 32,
            log_index=0,
            block_number=108,  # only 2 confirmations deep at head 110
            block_hash="0x" + "aa" * 32,
            to_address=ALICE_ADDR,
            asset_id=token.id,
            amount=ONE_ETH,
            status=DepositStatus.SEEN.value,
            user_id=alice.id,
        ),
    )
    await session.flush()

    assert await watcher.confirm_and_credit(session, client, confirmations=5) == 0
    deposit = (await session.execute(select(OnchainDeposit))).scalar_one()
    assert deposit.status == DepositStatus.SEEN.value
    available, pending = await ledger.balance(session, user=alice, asset=token)
    assert available == 0
    assert pending == ONE_ETH


@pytest.mark.asyncio
async def test_handle_reorgs_orphans_seen_deposit_on_hash_mismatch(session: AsyncSession) -> None:
    _native, token, alice = await _world(session)
    client = FakeChainClient(
        chain_id=CHAIN_ID,
        head=105,
        block_hashes={100: "0x" + "ff" * 32},  # canonical chain disagrees with the recorded hash
    )
    session.add(
        OnchainDeposit(
            chain_id=CHAIN_ID,
            tx_hash="0x" + "11" * 32,
            log_index=0,
            block_number=100,
            block_hash="0x" + "aa" * 32,
            to_address=ALICE_ADDR,
            asset_id=token.id,
            amount=ONE_ETH,
            status=DepositStatus.SEEN.value,
            user_id=alice.id,
        ),
    )
    await session.flush()

    report = await watcher.handle_reorgs(session, client, reorg_depth=50)
    assert report.orphaned == 1
    assert report.lowest_block == 100
    deposit = (await session.execute(select(OnchainDeposit))).scalar_one()
    assert deposit.status == DepositStatus.ORPHANED.value
    available, _ = await ledger.balance(session, user=alice, asset=token)
    assert available == 0  # never credited → nothing to reverse


@pytest.mark.asyncio
async def test_handle_reorgs_reverses_credited_deposit(session: AsyncSession) -> None:
    _native, token, alice = await _world(session)
    deposit = OnchainDeposit(
        chain_id=CHAIN_ID,
        tx_hash="0x" + "11" * 32,
        log_index=0,
        block_number=100,
        block_hash="0x" + "aa" * 32,
        to_address=ALICE_ADDR,
        asset_id=token.id,
        amount=ONE_ETH,
        status=DepositStatus.CREDITED.value,
        user_id=alice.id,
    )
    session.add(deposit)
    await session.flush()
    # Simulate the credit that confirm_and_credit would have posted.
    in_transit = await ledger.get_or_create_account(
        session, asset=token, name=ledger.DEPOSITS_IN_TRANSIT_ACCOUNT, owner_type="system",
    )
    wallet = await ledger.get_user_wallet_account(session, user=alice, asset=token)
    await ledger.post(
        session,
        transaction_type=LedgerEntryType.DEPOSIT,
        idempotency_key=f"deposit-credit:{deposit.id}",
        ref_type="onchain_deposit",
        ref_id=str(deposit.id),
        legs=[ledger.LedgerLeg(in_transit, token, -ONE_ETH), ledger.LedgerLeg(wallet, token, ONE_ETH)],
    )
    assert (await ledger.available_balance(session, user=alice, asset=token)) == ONE_ETH

    client = FakeChainClient(
        chain_id=CHAIN_ID,
        head=101,
        block_hashes={100: "0x" + "ff" * 32},  # reorged away
    )
    report = await watcher.handle_reorgs(session, client, reorg_depth=50)
    assert report.orphaned == 1

    refreshed = (await session.execute(select(OnchainDeposit))).scalar_one()
    assert refreshed.status == DepositStatus.ORPHANED.value
    assert (await ledger.available_balance(session, user=alice, asset=token)) == 0


@pytest.mark.asyncio
async def test_run_scan_records_and_credits_end_to_end(session: AsyncSession) -> None:
    _native, token, alice = await _world(session)
    block_hash = "0x" + "aa" * 32
    client = FakeChainClient(
        chain_id=CHAIN_ID,
        head=110,
        block_hashes={100: block_hash},
        erc20_transfers=[
            Erc20Transfer(
                token_address=TOKEN,
                from_address=SENDER,
                to_address=ALICE_ADDR,
                value=ONE_ETH,
                tx_hash="0x" + "11" * 32,
                log_index=2,
                block_number=100,
                block_hash=block_hash,
            ),
        ],
    )

    report = await watcher.run_scan(session, client, confirmations=5, reorg_depth=50)
    assert report.recorded == 1
    assert report.credited == 1
    assert report.orphaned == 0

    available, pending = await ledger.balance(session, user=alice, asset=token)
    assert available == ONE_ETH
    assert pending == 0

    cursor = await watcher.get_cursor(session, CHAIN_ID)
    assert cursor is not None
    assert cursor.last_scanned_block == 110


@pytest.mark.asyncio
async def test_confirm_and_credit_orphans_when_block_hash_no_longer_canonical(
    session: AsyncSession,
) -> None:
    _native, token, alice = await _world(session)
    # Deep enough to credit, but the canonical hash at credit time disagrees with what was recorded.
    client = FakeChainClient(chain_id=CHAIN_ID, head=120, block_hashes={100: "0x" + "ff" * 32})
    session.add(
        OnchainDeposit(
            chain_id=CHAIN_ID,
            tx_hash="0x" + "11" * 32,
            log_index=0,
            block_number=100,
            block_hash="0x" + "aa" * 32,
            to_address=ALICE_ADDR,
            asset_id=token.id,
            amount=ONE_ETH,
            status=DepositStatus.SEEN.value,
            user_id=alice.id,
        ),
    )
    await session.flush()

    credited = await watcher.confirm_and_credit(session, client, confirmations=5)
    assert credited == 0
    deposit = (await session.execute(select(OnchainDeposit))).scalar_one()
    assert deposit.status == DepositStatus.ORPHANED.value
    assert await ledger.available_balance(session, user=alice, asset=token) == 0


@pytest.mark.asyncio
async def test_reorg_recovery_orphan_then_recredit_same_tx(session: AsyncSession) -> None:
    _native, token, alice = await _world(session)
    tx_hash = "0x" + "11" * 32
    client = FakeChainClient(
        chain_id=CHAIN_ID,
        head=120,
        block_hashes={100: "0x" + "aa" * 32},
        erc20_transfers=[
            Erc20Transfer(
                token_address=TOKEN,
                from_address=SENDER,
                to_address=ALICE_ADDR,
                value=ONE_ETH,
                tx_hash=tx_hash,
                log_index=3,
                block_number=100,
                block_hash="0x" + "aa" * 32,
            ),
        ],
    )

    # 1. record + credit the deposit
    await watcher.record_deposits(session, client, from_block=1, to_block=120)
    assert await watcher.confirm_and_credit(session, client, confirmations=5) == 1
    assert await ledger.available_balance(session, user=alice, asset=token) == ONE_ETH

    # 2. a reorg replaces block 100 → the credited deposit is reversed
    client.head = 121
    client.block_hashes[100] = "0x" + "ff" * 32
    assert (await watcher.handle_reorgs(session, client, reorg_depth=50)).orphaned == 1
    assert await ledger.available_balance(session, user=alice, asset=token) == 0

    # 3. the SAME tx is re-mined at a new block/hash → the orphaned row is resurrected, not skipped
    client.head = 130
    client.erc20_transfers = [
        Erc20Transfer(
            token_address=TOKEN,
            from_address=SENDER,
            to_address=ALICE_ADDR,
            value=ONE_ETH,
            tx_hash=tx_hash,
            log_index=3,
            block_number=102,
            block_hash="0x" + "bb" * 32,
        ),
    ]
    client.block_hashes[102] = "0x" + "bb" * 32
    assert await watcher.record_deposits(session, client, from_block=1, to_block=130) == 1
    deposit = (await session.execute(select(OnchainDeposit))).scalar_one()
    assert deposit.status == DepositStatus.SEEN.value
    assert deposit.block_number == 102

    # 4. and it can be credited again (the resurrected row's bumped credit_revision makes a fresh key)
    assert await watcher.confirm_and_credit(session, client, confirmations=5) == 1
    assert await ledger.available_balance(session, user=alice, asset=token) == ONE_ETH


@pytest.mark.asyncio
async def test_reorg_recovery_recredits_when_block_reconverges_to_same_hash(
    session: AsyncSession,
) -> None:
    """#6: a reorg that re-converges to the ORIGINAL block hash must still re-credit the user.

    Keying the credit on block_hash made the second credit collide with the first idempotency key,
    so `ledger.post` returned the original transaction and posted nothing — the deposit was marked
    CREDITED with no ledger entry, permanently losing the user's funds.
    """
    _native, token, alice = await _world(session)
    tx_hash = "0x" + "11" * 32
    aa = "0x" + "aa" * 32
    client = FakeChainClient(
        chain_id=CHAIN_ID,
        head=120,
        block_hashes={100: aa},
        erc20_transfers=[
            Erc20Transfer(
                token_address=TOKEN,
                from_address=SENDER,
                to_address=ALICE_ADDR,
                value=ONE_ETH,
                tx_hash=tx_hash,
                log_index=3,
                block_number=100,
                block_hash=aa,
            ),
        ],
    )

    # 1. record + credit
    await watcher.record_deposits(session, client, from_block=1, to_block=120)
    assert await watcher.confirm_and_credit(session, client, confirmations=5) == 1
    assert await ledger.available_balance(session, user=alice, asset=token) == ONE_ETH

    # 2. a transient reorg flips block 100's hash → the credited deposit is reversed
    client.head = 121
    client.block_hashes[100] = "0x" + "ff" * 32
    assert (await watcher.handle_reorgs(session, client, reorg_depth=50)).orphaned == 1
    assert await ledger.available_balance(session, user=alice, asset=token) == 0

    # 3. the chain RE-CONVERGES: block 100 becomes canonical again at its ORIGINAL hash "aa"
    client.head = 130
    client.block_hashes[100] = aa
    assert await watcher.record_deposits(session, client, from_block=1, to_block=130) == 1
    deposit = (await session.execute(select(OnchainDeposit))).scalar_one()
    assert deposit.status == DepositStatus.SEEN.value

    # 4. it MUST be credited again, even though the block hash equals the original credit's
    assert await watcher.confirm_and_credit(session, client, confirmations=5) == 1
    assert await ledger.available_balance(session, user=alice, asset=token) == ONE_ETH


@pytest.mark.asyncio
async def test_run_scan_reverses_credited_deposit_on_later_reorg(session: AsyncSession) -> None:
    _native, token, alice = await _world(session)
    transfer = Erc20Transfer(
        token_address=TOKEN,
        from_address=SENDER,
        to_address=ALICE_ADDR,
        value=ONE_ETH,
        tx_hash="0x" + "11" * 32,
        log_index=2,
        block_number=100,
        block_hash="0x" + "aa" * 32,
    )
    # reorg_depth (2) is intentionally shallower than confirmations (5): a credited deposit must
    # still be reversible when the reorg lands shortly after crediting.
    client = FakeChainClient(
        chain_id=CHAIN_ID, head=105, block_hashes={100: "0x" + "aa" * 32}, erc20_transfers=[transfer],
    )
    first = await watcher.run_scan(session, client, confirmations=5, reorg_depth=2)
    assert first.credited == 1
    assert await ledger.available_balance(session, user=alice, asset=token) == ONE_ETH

    client.head = 106
    client.block_hashes[100] = "0x" + "ff" * 32
    second = await watcher.run_scan(session, client, confirmations=5, reorg_depth=2)
    assert second.orphaned == 1
    assert await ledger.available_balance(session, user=alice, asset=token) == 0


@pytest.mark.asyncio
async def test_run_scan_reverses_credit_within_finality_window_past_reorg_depth(
    session: AsyncSession,
) -> None:
    """#13: a credited deposit must stay reversible for a full finality depth past the credit point,
    not just `reorg_depth` blocks. A deep/late reorg beyond reorg_depth but within finality must
    still reverse the credit (otherwise the credit becomes an un-backed liability)."""
    _native, token, alice = await _world(session)
    transfer = Erc20Transfer(
        token_address=TOKEN,
        from_address=SENDER,
        to_address=ALICE_ADDR,
        value=ONE_ETH,
        tx_hash="0x" + "11" * 32,
        log_index=2,
        block_number=100,
        block_hash="0x" + "aa" * 32,
    )
    client = FakeChainClient(
        chain_id=CHAIN_ID, head=105, block_hashes={100: "0x" + "aa" * 32}, erc20_transfers=[transfer],
    )
    first = await watcher.run_scan(
        session, client, confirmations=5, reorg_depth=2, finality_depth=64,
    )
    assert first.credited == 1
    assert await ledger.available_balance(session, user=alice, asset=token) == ONE_ETH

    # The reorg lands 10 blocks past the credit — beyond reorg_depth(2) but within finality_depth(64).
    client.head = 115
    client.block_hashes[100] = "0x" + "ff" * 32
    second = await watcher.run_scan(
        session, client, confirmations=5, reorg_depth=2, finality_depth=64,
    )
    assert second.orphaned == 1
    assert await ledger.available_balance(session, user=alice, asset=token) == 0


@pytest.mark.asyncio
async def test_run_scan_rewinds_cursor_after_reorg(session: AsyncSession) -> None:
    _native, token, alice = await _world(session)
    transfer = Erc20Transfer(
        token_address=TOKEN,
        from_address=SENDER,
        to_address=ALICE_ADDR,
        value=ONE_ETH,
        tx_hash="0x" + "11" * 32,
        log_index=2,
        block_number=100,
        block_hash="0x" + "aa" * 32,
    )
    client = FakeChainClient(
        chain_id=CHAIN_ID, head=102, block_hashes={100: "0x" + "aa" * 32}, erc20_transfers=[transfer],
    )
    await watcher.run_scan(session, client, confirmations=5, reorg_depth=2)
    cursor = await watcher.get_cursor(session, CHAIN_ID)
    assert cursor is not None
    assert cursor.last_scanned_block == 102

    client.head = 103
    client.block_hashes[100] = "0x" + "ff" * 32  # block 100 reorged (still within the reorg window)
    await watcher.run_scan(session, client, confirmations=5, reorg_depth=2)
    cursor = await watcher.get_cursor(session, CHAIN_ID)
    assert cursor is not None
    # Cursor rewound below the orphaned block so the replacement block(s) get re-scanned.
    assert cursor.last_scanned_block <= 99
