"""Withdrawal processor.

One serialized worker per chain drains `withdrawal_requests`, assigns a hot-wallet nonce, signs
and broadcasts the payout, then (in a later pass) settles or reverses the ledger reservation based
on the on-chain receipt. Serialization per chain plus a persisted `hot_wallet_nonces` counter keeps
nonces gap-free; a send only consumes a nonce once it actually broadcasts.

Selection uses `FOR UPDATE SKIP LOCKED` on Postgres so multiple processes never grab the same row;
on SQLite (tests) the lock clause is skipped. Chain I/O goes through the injected `SenderClient`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chain.client import ChainRpcError
from app.core.enums import LedgerEntryType, WithdrawalStatus
from app.models.tables import Asset, User, WithdrawalRequest
from app.services import ledger
from worker._nonce import nonce_row, supports_skip_locked

if TYPE_CHECKING:
    from app.chain.types import SenderClient, SignedTx

logger = logging.getLogger("kasa.worker.withdrawer")

_WITHDRAWAL_REF_TYPE = "withdrawal_request"
_DEFAULT_BATCH = 20


async def _load_asset(session: AsyncSession, asset_id: UUID) -> Asset:
    return (await session.execute(select(Asset).where(Asset.id == asset_id))).scalar_one()


async def _load_user(session: AsyncSession, user_id: UUID) -> User:
    return (await session.execute(select(User).where(User.id == user_id))).scalar_one()


async def _claim_pending(
    session: AsyncSession,
    chain_id: int,
    batch: int,
) -> list[WithdrawalRequest]:
    statement: Select[tuple[WithdrawalRequest]] = (
        select(WithdrawalRequest)
        .where(
            WithdrawalRequest.chain_id == chain_id,
            WithdrawalRequest.status.in_(
                [WithdrawalStatus.REQUESTED.value, WithdrawalStatus.APPROVED.value],
            ),
        )
        .order_by(WithdrawalRequest.created_at, WithdrawalRequest.id)
        .limit(batch)
    )
    if supports_skip_locked(session):
        statement = statement.with_for_update(skip_locked=True)
    return list((await session.execute(statement)).scalars())


def _sign(
    client: SenderClient,
    *,
    asset: Asset,
    request: WithdrawalRequest,
    private_key: str,
    nonce: int,
    gas_price: int,
) -> SignedTx:
    amount = int(request.amount)
    if asset.type == "native":
        return client.sign_native(
            private_key=private_key,
            to_address=request.to_address,
            value=amount,
            nonce=nonce,
            gas_price=gas_price,
        )
    if asset.type == "erc20" and asset.contract_address is not None:
        return client.sign_erc20(
            private_key=private_key,
            token_address=asset.contract_address,
            to_address=request.to_address,
            value=amount,
            nonce=nonce,
            gas_price=gas_price,
        )
    msg = f"withdrawal asset {asset.id} ({asset.type}) is not withdrawable"
    raise ValueError(msg)


async def _reverse_reservation(
    session: AsyncSession,
    request: WithdrawalRequest,
    error: str,
) -> None:
    asset = await _load_asset(session, request.asset_id)
    user = await _load_user(session, request.user_id)
    amount = int(request.amount)
    reserved = await ledger.get_or_create_account(
        session, asset=asset, name=ledger.WITHDRAWALS_RESERVED_ACCOUNT, owner_type="system",
    )
    wallet = await ledger.get_user_wallet_account(session, user=user, asset=asset)
    await ledger.post(
        session,
        transaction_type=LedgerEntryType.REVERSAL,
        idempotency_key=f"withdrawal-reverse:{request.id}",
        ref_type=_WITHDRAWAL_REF_TYPE,
        ref_id=str(request.id),
        legs=[ledger.LedgerLeg(reserved, asset, -amount), ledger.LedgerLeg(wallet, asset, amount)],
    )
    request.status = WithdrawalStatus.FAILED.value
    request.error = error


async def _settle(session: AsyncSession, request: WithdrawalRequest) -> None:
    asset = await _load_asset(session, request.asset_id)
    amount = int(request.amount)
    reserved = await ledger.get_or_create_account(
        session, asset=asset, name=ledger.WITHDRAWALS_RESERVED_ACCOUNT, owner_type="system",
    )
    settled = await ledger.get_or_create_account(
        session, asset=asset, name=ledger.WITHDRAWALS_SETTLED_ACCOUNT, owner_type="system",
    )
    await ledger.post(
        session,
        transaction_type=LedgerEntryType.WITHDRAWAL,
        idempotency_key=f"withdrawal-settle:{request.id}",
        ref_type=_WITHDRAWAL_REF_TYPE,
        ref_id=str(request.id),
        legs=[ledger.LedgerLeg(reserved, asset, -amount), ledger.LedgerLeg(settled, asset, amount)],
    )


async def sign_pending(
    session: AsyncSession,
    client: SenderClient,
    *,
    hot_wallet_key: str,
    hot_wallet_address: str,
    batch: int = _DEFAULT_BATCH,
) -> int:
    """Phase 1 (durable): claim pending requests, assign a gap-free nonce, SIGN, and persist the
    signed raw tx + nonce + hash with status SIGNING. Nothing is broadcast here — once this commits,
    the exact payout is fixed, so a later broadcast (even after a crash) re-sends the identical tx.
    """
    requests = await _claim_pending(session, client.chain_id, batch)
    if not requests:
        return 0
    hot_nonce = await nonce_row(session, client, hot_wallet_address)
    gas_price = client.suggested_gas_price()
    signed = 0
    for request in requests:
        nonce = hot_nonce.next_nonce
        try:
            asset = await _load_asset(session, request.asset_id)
            request.attempts += 1
            tx = _sign(
                client,
                asset=asset,
                request=request,
                private_key=hot_wallet_key,
                nonce=nonce,
                gas_price=gas_price,
            )
        except ValueError as exc:
            # Asset not withdrawable → this request can never be signed; refund the reservation.
            await _reverse_reservation(session, request, str(exc))
            continue
        except Exception:
            logger.exception(
                "withdrawal %s failed pre-sign on chain %s", request.id, client.chain_id,
            )
            continue
        request.signed_tx = tx.raw
        request.tx_hash = tx.tx_hash
        request.nonce = nonce
        request.status = WithdrawalStatus.SIGNING.value
        hot_nonce.next_nonce = nonce + 1
        signed += 1
    await session.flush()
    return signed


async def broadcast_signed(session: AsyncSession, client: SenderClient) -> int:
    """Phase 2: broadcast every persisted SIGNING request (in nonce order). A broadcast that fails
    is left SIGNING and retried next pass — the durable signed tx is never abandoned and never
    re-signed, so a payout can't be double-sent or stranded. Refunds happen only via the dropped-tx
    reconcile when a *different* tx supersedes the nonce (#3)."""
    requests = list(
        (
            await session.execute(
                select(WithdrawalRequest)
                .where(
                    WithdrawalRequest.chain_id == client.chain_id,
                    WithdrawalRequest.status == WithdrawalStatus.SIGNING.value,
                )
                .order_by(WithdrawalRequest.nonce),
            )
        ).scalars(),
    )
    broadcast = 0
    for request in requests:
        if request.signed_tx is None:
            continue
        try:
            request.tx_hash = client.broadcast_raw(request.signed_tx)
        except ChainRpcError:
            logger.warning("withdrawal %s broadcast failed; will retry next pass", request.id)
            continue
        request.status = WithdrawalStatus.BROADCAST.value
        broadcast += 1
    await session.flush()
    return broadcast


async def broadcast_pending(
    session: AsyncSession,
    client: SenderClient,
    *,
    hot_wallet_key: str,
    hot_wallet_address: str,
    batch: int = _DEFAULT_BATCH,
) -> int:
    """Sign-then-broadcast in one session. Production (worker.main) runs the two phases in SEPARATE
    committed transactions so a crash between them re-broadcasts the durable signed tx rather than
    re-signing at a fresh nonce; this combined helper is for the happy-path call/tests."""
    await sign_pending(
        session,
        client,
        hot_wallet_key=hot_wallet_key,
        hot_wallet_address=hot_wallet_address,
        batch=batch,
    )
    return await broadcast_signed(session, client)


async def confirm_broadcast(
    session: AsyncSession,
    client: SenderClient,
    *,
    confirmations: int,
    hot_wallet_address: str | None = None,
) -> int:
    head = client.block_number()
    requests = list(
        (
            await session.execute(
                select(WithdrawalRequest).where(
                    WithdrawalRequest.chain_id == client.chain_id,
                    WithdrawalRequest.status == WithdrawalStatus.BROADCAST.value,
                ),
            )
        ).scalars(),
    )
    settled = 0
    for request in requests:
        if request.tx_hash is None:
            continue
        receipt = client.get_receipt(request.tx_hash)
        if receipt is None:
            await _reconcile_unmined(
                session,
                client,
                request,
                hot_wallet_address,
                head=head,
                confirmations=confirmations,
            )
            continue
        request.unmined_since_block = None
        # Do not act on a receipt until it is buried under `confirmations` blocks AND its block is
        # still canonical (finding #7). A fresh or reorged-out receipt is left BROADCAST and
        # re-evaluated next pass — so a payout reorged away within the confirmation window is never
        # permanently settled, and a still-pending tx is never wrongly reversed.
        if head - receipt.block_number < confirmations:
            continue
        canonical = client.block_hash(receipt.block_number)
        if canonical is None or canonical != receipt.block_hash:
            continue
        if receipt.status == 1:
            await _settle(session, request)
            request.status = WithdrawalStatus.CONFIRMED.value
            settled += 1
        else:
            await _reverse_reservation(session, request, "transaction reverted on-chain")
    await session.flush()
    return settled


async def _reconcile_unmined(  # noqa: PLR0913
    session: AsyncSession,
    client: SenderClient,
    request: WithdrawalRequest,
    hot_wallet_address: str | None,
    *,
    head: int,
    confirmations: int,
) -> None:
    """A broadcast tx with no receipt may be pending, dropped, or freshly mined on a lagging RPC.

    Only reverse after the mined nonce has advanced past ours and the receipt stays absent for the
    same confirmation depth used by settlement. A later receipt clears the marker.
    """
    if hot_wallet_address is None or request.nonce is None:
        return
    if client.latest_nonce(hot_wallet_address) <= request.nonce:
        request.unmined_since_block = None
        return
    if request.unmined_since_block is None:
        request.unmined_since_block = head
        return
    if head - request.unmined_since_block >= confirmations:
        await _reverse_reservation(session, request, "transaction dropped (nonce superseded)")
