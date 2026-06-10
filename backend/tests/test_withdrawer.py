import uuid

import pytest

pytest.importorskip("aiosqlite")

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chain.types import TxReceipt
from app.core.enums import LedgerEntryType, WithdrawalStatus
from app.models.tables import Asset, HotWalletNonce, User, WithdrawalRequest
from app.services import ledger
from app.services.withdrawal_service import create_withdrawal
from tests.support import FakeChainClient, seed_asset, seed_user
from worker import withdrawer

CHAIN_ID = 11_155_111
HOT_ADDR = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
HOT_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
EXTERNAL = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"  # valid EIP-55 destination
TOKEN = "0x5FbDB2315678afecb367f032d93F642f64180aa3"
ONE_ETH = 500_000_000_000_000


async def _fund_wallet(session: AsyncSession, user: User, asset: Asset, amount: int) -> None:
    source = await ledger.get_or_create_account(
        session, asset=asset, name="test_source", owner_type="system",
    )
    wallet = await ledger.get_user_wallet_account(session, user=user, asset=asset)
    await ledger.post(
        session,
        transaction_type=LedgerEntryType.DEPOSIT,
        idempotency_key=f"fund:{user.id}:{asset.id}",
        ref_type="test",
        ref_id="fund",
        legs=[ledger.LedgerLeg(source, asset, -amount), ledger.LedgerLeg(wallet, asset, amount)],
    )


async def _request_withdrawal(
    session: AsyncSession,
    user: User,
    asset: Asset,
    amount: int,
) -> WithdrawalRequest:
    response = await create_withdrawal(
        session,
        user=user,
        asset_id=asset.id,
        to_address=EXTERNAL,
        amount=amount,
        idempotency_key=f"wd:{uuid.uuid4()}",
    )
    return (
        await session.execute(select(WithdrawalRequest).where(WithdrawalRequest.id == response.id))
    ).scalar_one()


@pytest.mark.asyncio
async def test_broadcast_signs_sends_and_advances_nonce(session: AsyncSession) -> None:
    asset = await seed_asset(session, chain_id=CHAIN_ID, asset_type="native", symbol="ETH", decimals=18)
    user = await seed_user(session, email="a@example.com", hd_index=1)
    await _fund_wallet(session, user, asset, ONE_ETH)
    request = await _request_withdrawal(session, user, asset, ONE_ETH)
    assert await ledger.available_balance(session, user=user, asset=asset) == 0

    client = FakeChainClient(chain_id=CHAIN_ID, nonces={HOT_ADDR.lower(): 7})
    sent = await withdrawer.broadcast_pending(
        session, client, hot_wallet_key=HOT_KEY, hot_wallet_address=HOT_ADDR,
    )
    assert sent == 1

    await session.refresh(request)
    assert request.status == WithdrawalStatus.BROADCAST.value
    assert request.nonce == 7
    assert request.tx_hash is not None
    assert len(client.sent) == 1
    assert client.sent[0].kind == "native"
    assert client.sent[0].to_address == EXTERNAL
    assert client.sent[0].value == ONE_ETH
    assert client.sent[0].nonce == 7

    nonce_row = (
        await session.execute(select(HotWalletNonce).where(HotWalletNonce.chain_id == CHAIN_ID))
    ).scalar_one()
    assert nonce_row.next_nonce == 8


@pytest.mark.asyncio
async def test_broadcast_two_requests_use_sequential_nonces(session: AsyncSession) -> None:
    asset = await seed_asset(session, chain_id=CHAIN_ID, asset_type="native", symbol="ETH", decimals=18)
    user = await seed_user(session, email="a@example.com", hd_index=1)
    await _fund_wallet(session, user, asset, 5 * ONE_ETH)
    await _request_withdrawal(session, user, asset, ONE_ETH)
    await _request_withdrawal(session, user, asset, 2 * ONE_ETH)

    client = FakeChainClient(chain_id=CHAIN_ID, nonces={HOT_ADDR.lower(): 7})
    sent = await withdrawer.broadcast_pending(
        session, client, hot_wallet_key=HOT_KEY, hot_wallet_address=HOT_ADDR,
    )
    assert sent == 2
    assert sorted(tx.nonce for tx in client.sent) == [7, 8]

    nonce_row = (
        await session.execute(select(HotWalletNonce).where(HotWalletNonce.chain_id == CHAIN_ID))
    ).scalar_one()
    assert nonce_row.next_nonce == 9


@pytest.mark.asyncio
async def test_broadcast_erc20_uses_token_transfer(session: AsyncSession) -> None:
    asset = await seed_asset(
        session,
        chain_id=CHAIN_ID,
        asset_type="erc20",
        symbol="DEMO",
        decimals=18,
        contract_address=TOKEN,
    )
    user = await seed_user(session, email="a@example.com", hd_index=1)
    await _fund_wallet(session, user, asset, ONE_ETH)
    await _request_withdrawal(session, user, asset, ONE_ETH)

    client = FakeChainClient(chain_id=CHAIN_ID, nonces={HOT_ADDR.lower(): 0})
    await withdrawer.broadcast_pending(
        session, client, hot_wallet_key=HOT_KEY, hot_wallet_address=HOT_ADDR,
    )
    assert client.sent[0].kind == "erc20"
    assert client.sent[0].token_address == TOKEN
    assert client.sent[0].to_address == EXTERNAL


@pytest.mark.asyncio
async def test_confirm_settles_on_success(session: AsyncSession) -> None:
    asset = await seed_asset(session, chain_id=CHAIN_ID, asset_type="native", symbol="ETH", decimals=18)
    user = await seed_user(session, email="a@example.com", hd_index=1)
    await _fund_wallet(session, user, asset, ONE_ETH)
    request = await _request_withdrawal(session, user, asset, ONE_ETH)

    client = FakeChainClient(chain_id=CHAIN_ID, nonces={HOT_ADDR.lower(): 0})
    await withdrawer.broadcast_pending(
        session, client, hot_wallet_key=HOT_KEY, hot_wallet_address=HOT_ADDR,
    )
    await session.refresh(request)
    assert request.tx_hash is not None
    block_hash = "0x" + "ab" * 32
    client.receipts[request.tx_hash] = TxReceipt(
        tx_hash=request.tx_hash, status=1, block_number=10, block_hash=block_hash,
    )
    client.head = 100  # buried well past the confirmation depth
    client.block_hashes[10] = block_hash  # still canonical

    settled = await withdrawer.confirm_broadcast(session, client, confirmations=5)
    assert settled == 1
    await session.refresh(request)
    assert request.status == WithdrawalStatus.CONFIRMED.value
    # Funds left the platform: user stays debited, reserve cleared to the settled sink.
    assert await ledger.available_balance(session, user=user, asset=asset) == 0
    reserved = await ledger.get_or_create_account(
        session, asset=asset, name=ledger.WITHDRAWALS_RESERVED_ACCOUNT, owner_type="system",
    )
    reserved_balance = await _account_balance(session, reserved.id)
    assert reserved_balance == 0


@pytest.mark.asyncio
async def test_confirm_reverses_on_revert(session: AsyncSession) -> None:
    asset = await seed_asset(session, chain_id=CHAIN_ID, asset_type="native", symbol="ETH", decimals=18)
    user = await seed_user(session, email="a@example.com", hd_index=1)
    await _fund_wallet(session, user, asset, ONE_ETH)
    request = await _request_withdrawal(session, user, asset, ONE_ETH)

    client = FakeChainClient(chain_id=CHAIN_ID, nonces={HOT_ADDR.lower(): 0})
    await withdrawer.broadcast_pending(
        session, client, hot_wallet_key=HOT_KEY, hot_wallet_address=HOT_ADDR,
    )
    await session.refresh(request)
    assert request.tx_hash is not None
    block_hash = "0x" + "ab" * 32
    client.receipts[request.tx_hash] = TxReceipt(
        tx_hash=request.tx_hash, status=0, block_number=10, block_hash=block_hash,
    )
    client.head = 100
    client.block_hashes[10] = block_hash

    await withdrawer.confirm_broadcast(session, client, confirmations=5)
    await session.refresh(request)
    assert request.status == WithdrawalStatus.FAILED.value
    # Reverted on-chain → the reservation is returned to the user.
    assert await ledger.available_balance(session, user=user, asset=asset) == ONE_ETH


@pytest.mark.asyncio
async def test_broadcast_failure_holds_signed_tx_for_retry(session: AsyncSession) -> None:
    """#3: a transient broadcast failure must NOT refund. The tx is already signed + persisted, so
    it stays SIGNING (funds reserved, nonce consumed) and is re-broadcast next pass — refunds happen
    only via the dropped-tx reconcile, never on a flaky send."""
    asset = await seed_asset(session, chain_id=CHAIN_ID, asset_type="native", symbol="ETH", decimals=18)
    user = await seed_user(session, email="a@example.com", hd_index=1)
    await _fund_wallet(session, user, asset, ONE_ETH)
    request = await _request_withdrawal(session, user, asset, ONE_ETH)

    client = FakeChainClient(
        chain_id=CHAIN_ID, nonces={HOT_ADDR.lower(): 7}, send_error="rpc down",
    )
    broadcast = await withdrawer.broadcast_pending(
        session, client, hot_wallet_key=HOT_KEY, hot_wallet_address=HOT_ADDR,
    )
    assert broadcast == 0
    assert client.sent == []  # the network rejected the broadcast
    await session.refresh(request)
    # Signed + durable, awaiting re-broadcast — not failed, not refunded.
    assert request.status == WithdrawalStatus.SIGNING.value
    assert request.signed_tx is not None
    assert request.nonce == 7
    assert await ledger.available_balance(session, user=user, asset=asset) == 0
    # The nonce was durably consumed; the retry must reuse it, not allocate a fresh one.
    nonce_row = (
        await session.execute(select(HotWalletNonce).where(HotWalletNonce.chain_id == CHAIN_ID))
    ).scalar_one()
    assert nonce_row.next_nonce == 8

    # Next pass, the chain recovers → the SAME signed tx broadcasts (same nonce), nonce not re-bumped.
    client.send_error = None
    broadcast = await withdrawer.broadcast_signed(session, client)
    assert broadcast == 1
    await session.refresh(request)
    assert request.status == WithdrawalStatus.BROADCAST.value
    assert request.nonce == 7
    assert client.sent[0].nonce == 7
    nonce_row = (
        await session.execute(select(HotWalletNonce).where(HotWalletNonce.chain_id == CHAIN_ID))
    ).scalar_one()
    assert nonce_row.next_nonce == 8


@pytest.mark.asyncio
async def test_crash_between_sign_and_broadcast_rebroadcasts_the_same_tx(session: AsyncSession) -> None:
    """#3: signing persists the nonce + raw tx durably. A re-broadcast after a 'crash' (status not
    committed) re-sends the IDENTICAL tx at the SAME nonce and never re-signs or re-bumps the nonce —
    so a payout can never be sent twice at two different nonces."""
    asset = await seed_asset(session, chain_id=CHAIN_ID, asset_type="native", symbol="ETH", decimals=18)
    user = await seed_user(session, email="a@example.com", hd_index=1)
    await _fund_wallet(session, user, asset, ONE_ETH)
    request = await _request_withdrawal(session, user, asset, ONE_ETH)

    client = FakeChainClient(chain_id=CHAIN_ID, nonces={HOT_ADDR.lower(): 5})

    # Phase 1: sign + persist (this is what a real worker commits before broadcasting).
    assert await withdrawer.sign_pending(
        session, client, hot_wallet_key=HOT_KEY, hot_wallet_address=HOT_ADDR,
    ) == 1
    await session.refresh(request)
    assert request.status == WithdrawalStatus.SIGNING.value
    assert request.signed_tx is not None
    assert request.nonce == 5
    expected_hash = request.tx_hash

    # Phase 2: broadcast, but simulate a crash that loses the BROADCAST status (revert to SIGNING).
    assert await withdrawer.broadcast_signed(session, client) == 1
    request.status = WithdrawalStatus.SIGNING.value
    await session.flush()

    # Recovery: broadcast again. Same signed tx, same nonce, same hash; the nonce counter is untouched.
    assert await withdrawer.broadcast_signed(session, client) == 1
    await session.refresh(request)
    assert request.tx_hash == expected_hash
    assert request.nonce == 5
    assert [tx.nonce for tx in client.sent] == [5, 5]  # the identical tx, re-sent — not two nonces
    nonce_row = (
        await session.execute(select(HotWalletNonce).where(HotWalletNonce.chain_id == CHAIN_ID))
    ).scalar_one()
    assert nonce_row.next_nonce == 6  # never advanced by the re-broadcast


@pytest.mark.asyncio
async def test_broadcast_isolates_a_failing_request_from_healthy_ones(session: AsyncSession) -> None:
    asset = await seed_asset(session, chain_id=CHAIN_ID, asset_type="native", symbol="ETH", decimals=18)
    user = await seed_user(session, email="a@example.com", hd_index=1)
    await _fund_wallet(session, user, asset, ONE_ETH)
    healthy = await _request_withdrawal(session, user, asset, ONE_ETH)
    # A poisoned request whose asset row does not exist (would raise NoResultFound on load).
    poisoned = WithdrawalRequest(
        user_id=user.id,
        asset_id=uuid.uuid4(),
        chain_id=CHAIN_ID,
        to_address=EXTERNAL,
        amount=ONE_ETH,
        status=WithdrawalStatus.REQUESTED.value,
    )
    session.add(poisoned)
    await session.flush()

    client = FakeChainClient(chain_id=CHAIN_ID, nonces={HOT_ADDR.lower(): 0})
    sent = await withdrawer.broadcast_pending(
        session, client, hot_wallet_key=HOT_KEY, hot_wallet_address=HOT_ADDR,
    )
    # The healthy request still broadcasts; the poisoned one is skipped, not reversed, not aborting.
    assert sent == 1
    await session.refresh(healthy)
    assert healthy.status == WithdrawalStatus.BROADCAST.value
    await session.refresh(poisoned)
    assert poisoned.status == WithdrawalStatus.REQUESTED.value


@pytest.mark.asyncio
async def test_confirm_reconciles_dropped_tx_when_nonce_advanced(session: AsyncSession) -> None:
    asset = await seed_asset(session, chain_id=CHAIN_ID, asset_type="native", symbol="ETH", decimals=18)
    user = await seed_user(session, email="a@example.com", hd_index=1)
    await _fund_wallet(session, user, asset, ONE_ETH)
    request = await _request_withdrawal(session, user, asset, ONE_ETH)

    client = FakeChainClient(chain_id=CHAIN_ID, nonces={HOT_ADDR.lower(): 0})
    await withdrawer.broadcast_pending(
        session, client, hot_wallet_key=HOT_KEY, hot_wallet_address=HOT_ADDR,
    )
    # Our tx (nonce 0) never mined and the *mined* nonce has moved past it -> the tx was dropped.
    client.latest_nonces[HOT_ADDR.lower()] = 1  # mined nonce advanced past our request.nonce 0
    first_unmined_head = 20
    client.head = first_unmined_head

    settled = await withdrawer.confirm_broadcast(
        session, client, confirmations=5, hot_wallet_address=HOT_ADDR,
    )
    assert settled == 0
    await session.refresh(request)
    assert request.status == WithdrawalStatus.BROADCAST.value
    assert request.unmined_since_block == first_unmined_head
    assert await ledger.available_balance(session, user=user, asset=asset) == 0

    client.head = 25
    settled = await withdrawer.confirm_broadcast(
        session, client, confirmations=5, hot_wallet_address=HOT_ADDR,
    )
    assert settled == 0
    await session.refresh(request)
    assert request.status == WithdrawalStatus.FAILED.value
    assert request.error == "transaction dropped (nonce superseded)"
    # Dropped -> reservation returned to the user.
    assert await ledger.available_balance(session, user=user, asset=asset) == ONE_ETH


@pytest.mark.asyncio
async def test_confirm_does_not_reverse_mined_tx_with_lagging_receipt(
    session: AsyncSession,
) -> None:
    client, request, asset, user = await _broadcast_one(session)
    assert request.tx_hash is not None
    client.latest_nonces[HOT_ADDR.lower()] = 1
    first_unmined_head = 20
    client.head = first_unmined_head

    settled = await withdrawer.confirm_broadcast(
        session, client, confirmations=5, hot_wallet_address=HOT_ADDR,
    )

    assert settled == 0
    await session.refresh(request)
    assert request.status == WithdrawalStatus.BROADCAST.value
    assert request.unmined_since_block == first_unmined_head
    assert await ledger.available_balance(session, user=user, asset=asset) == 0
    reserved = await ledger.get_or_create_account(
        session, asset=asset, name=ledger.WITHDRAWALS_RESERVED_ACCOUNT, owner_type="system",
    )
    assert await _account_balance(session, reserved.id) == ONE_ETH

    block_hash = "0x" + "ab" * 32
    client.receipts[request.tx_hash] = TxReceipt(
        tx_hash=request.tx_hash,
        status=1,
        block_number=21,
        block_hash=block_hash,
    )
    client.head = 30
    client.block_hashes[21] = block_hash

    settled = await withdrawer.confirm_broadcast(
        session, client, confirmations=5, hot_wallet_address=HOT_ADDR,
    )

    assert settled == 1
    await session.refresh(request)
    assert request.status == WithdrawalStatus.CONFIRMED.value
    cleared_marker: int | None = request.unmined_since_block
    assert cleared_marker is None
    assert await ledger.available_balance(session, user=user, asset=asset) == 0
    assert await _account_balance(session, reserved.id) == 0


@pytest.mark.asyncio
async def test_confirm_reverses_dropped_tx_after_unmined_grace_window(
    session: AsyncSession,
) -> None:
    client, request, asset, user = await _broadcast_one(session)
    client.latest_nonces[HOT_ADDR.lower()] = 1
    first_unmined_head = 40
    client.head = first_unmined_head

    settled = await withdrawer.confirm_broadcast(
        session, client, confirmations=6, hot_wallet_address=HOT_ADDR,
    )

    assert settled == 0
    await session.refresh(request)
    assert request.status == WithdrawalStatus.BROADCAST.value
    assert request.unmined_since_block == first_unmined_head
    assert await ledger.available_balance(session, user=user, asset=asset) == 0

    client.head = 46
    settled = await withdrawer.confirm_broadcast(
        session, client, confirmations=6, hot_wallet_address=HOT_ADDR,
    )

    assert settled == 0
    await session.refresh(request)
    assert request.status == WithdrawalStatus.FAILED.value
    assert request.error == "transaction dropped (nonce superseded)"
    assert await ledger.available_balance(session, user=user, asset=asset) == ONE_ETH


@pytest.mark.asyncio
async def test_confirm_skips_pending_receipt(session: AsyncSession) -> None:
    asset = await seed_asset(session, chain_id=CHAIN_ID, asset_type="native", symbol="ETH", decimals=18)
    user = await seed_user(session, email="a@example.com", hd_index=1)
    await _fund_wallet(session, user, asset, ONE_ETH)
    request = await _request_withdrawal(session, user, asset, ONE_ETH)

    client = FakeChainClient(chain_id=CHAIN_ID, nonces={HOT_ADDR.lower(): 0})
    await withdrawer.broadcast_pending(
        session, client, hot_wallet_key=HOT_KEY, hot_wallet_address=HOT_ADDR,
    )
    # No receipt registered → still mining.
    settled = await withdrawer.confirm_broadcast(session, client, confirmations=5)
    assert settled == 0
    await session.refresh(request)
    assert request.status == WithdrawalStatus.BROADCAST.value


async def _broadcast_one(
    session: AsyncSession,
) -> tuple[FakeChainClient, WithdrawalRequest, Asset, User]:
    asset = await seed_asset(session, chain_id=CHAIN_ID, asset_type="native", symbol="ETH", decimals=18)
    user = await seed_user(session, email="a@example.com", hd_index=1)
    await _fund_wallet(session, user, asset, ONE_ETH)
    request = await _request_withdrawal(session, user, asset, ONE_ETH)
    client = FakeChainClient(chain_id=CHAIN_ID, nonces={HOT_ADDR.lower(): 0})
    await withdrawer.broadcast_pending(
        session, client, hot_wallet_key=HOT_KEY, hot_wallet_address=HOT_ADDR,
    )
    await session.refresh(request)
    return client, request, asset, user


@pytest.mark.asyncio
async def test_confirm_waits_for_confirmation_depth_before_settling(session: AsyncSession) -> None:
    """#7: a receipt at the chain head must NOT settle — settle only once buried under N confs."""
    client, request, asset, user = await _broadcast_one(session)
    assert request.tx_hash is not None
    block_hash = "0x" + "cd" * 32
    client.receipts[request.tx_hash] = TxReceipt(
        tx_hash=request.tx_hash, status=1, block_number=98, block_hash=block_hash,
    )
    client.head = 100  # only 2 confirmations deep
    client.block_hashes[98] = block_hash

    settled = await withdrawer.confirm_broadcast(session, client, confirmations=12)
    assert settled == 0
    await session.refresh(request)
    assert request.status == WithdrawalStatus.BROADCAST.value  # still pending, not settled
    # The user stays debited (reservation intact) — neither settled nor refunded yet.
    assert await ledger.available_balance(session, user=user, asset=asset) == 0


@pytest.mark.asyncio
async def test_confirm_does_not_settle_a_reorged_out_receipt(session: AsyncSession) -> None:
    """#7: a buried receipt whose block is no longer canonical must NOT settle (reorg guard)."""
    client, request, asset, user = await _broadcast_one(session)
    assert request.tx_hash is not None
    client.receipts[request.tx_hash] = TxReceipt(
        tx_hash=request.tx_hash, status=1, block_number=88, block_hash="0x" + "ab" * 32,
    )
    client.head = 100  # buried past 5 confirmations...
    client.block_hashes[88] = "0x" + "ff" * 32  # ...but block 88's canonical hash changed (reorg)

    settled = await withdrawer.confirm_broadcast(session, client, confirmations=5)
    assert settled == 0
    await session.refresh(request)
    assert request.status == WithdrawalStatus.BROADCAST.value  # held, not wrongly settled
    assert await ledger.available_balance(session, user=user, asset=asset) == 0


@pytest.mark.asyncio
async def test_confirm_settles_once_buried_and_canonical(session: AsyncSession) -> None:
    """#7: settle only when buried under N confs AND the receipt's block is still canonical."""
    client, request, asset, user = await _broadcast_one(session)
    assert request.tx_hash is not None
    block_hash = "0x" + "ab" * 32
    client.receipts[request.tx_hash] = TxReceipt(
        tx_hash=request.tx_hash, status=1, block_number=88, block_hash=block_hash,
    )
    client.head = 100
    client.block_hashes[88] = block_hash

    settled = await withdrawer.confirm_broadcast(session, client, confirmations=5)
    assert settled == 1
    await session.refresh(request)
    assert request.status == WithdrawalStatus.CONFIRMED.value
    assert await ledger.available_balance(session, user=user, asset=asset) == 0


@pytest.mark.asyncio
async def test_nonce_reconciles_to_chain_when_persisted_counter_is_stale(session: AsyncSession) -> None:
    """#12: if the persisted next_nonce is behind the chain (out-of-band tx, or a lost increment),
    the worker must advance to the chain's nonce instead of broadcasting at a stale, already-mined
    nonce that silently no-ops and wedges the whole queue."""
    asset = await seed_asset(session, chain_id=CHAIN_ID, asset_type="native", symbol="ETH", decimals=18)
    user = await seed_user(session, email="a@example.com", hd_index=1)
    await _fund_wallet(session, user, asset, ONE_ETH)
    await _request_withdrawal(session, user, asset, ONE_ETH)
    session.add(HotWalletNonce(chain_id=CHAIN_ID, address=HOT_ADDR, next_nonce=5))  # stale
    await session.flush()

    client = FakeChainClient(chain_id=CHAIN_ID, nonces={HOT_ADDR.lower(): 8})  # chain is really at 8
    await withdrawer.broadcast_pending(
        session, client, hot_wallet_key=HOT_KEY, hot_wallet_address=HOT_ADDR,
    )
    assert client.sent[0].nonce == 8
    nonce_row = (
        await session.execute(select(HotWalletNonce).where(HotWalletNonce.chain_id == CHAIN_ID))
    ).scalar_one()
    assert nonce_row.next_nonce == 9


@pytest.mark.asyncio
async def test_nonce_resets_when_hot_wallet_address_changes(session: AsyncSession) -> None:
    """#5: after a key rotation the persisted counter belongs to the OLD wallet. The new wallet must
    start from its own on-chain nonce, not inherit the old wallet's (which would strand withdrawals)."""
    asset = await seed_asset(session, chain_id=CHAIN_ID, asset_type="native", symbol="ETH", decimals=18)
    user = await seed_user(session, email="a@example.com", hd_index=1)
    await _fund_wallet(session, user, asset, ONE_ETH)
    await _request_withdrawal(session, user, asset, ONE_ETH)
    old_address = "0x000000000000000000000000000000000000dEaD"
    session.add(HotWalletNonce(chain_id=CHAIN_ID, address=old_address, next_nonce=20))
    await session.flush()

    client = FakeChainClient(chain_id=CHAIN_ID, nonces={HOT_ADDR.lower(): 3})
    await withdrawer.broadcast_pending(
        session, client, hot_wallet_key=HOT_KEY, hot_wallet_address=HOT_ADDR,
    )
    assert client.sent[0].nonce == 3  # new wallet's chain nonce, not the inherited 20
    nonce_row = (
        await session.execute(select(HotWalletNonce).where(HotWalletNonce.chain_id == CHAIN_ID))
    ).scalar_one()
    assert nonce_row.address == HOT_ADDR
    assert nonce_row.next_nonce == 4


async def _account_balance(session: AsyncSession, account_id: uuid.UUID) -> int:
    from sqlalchemy import func

    from app.models.tables import LedgerEntry

    return int(
        (
            await session.execute(
                select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
                    LedgerEntry.account_id == account_id,
                ),
            )
        ).scalar_one(),
    )
