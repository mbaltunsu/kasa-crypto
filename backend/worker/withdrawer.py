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
from app.models.tables import Asset, HotWalletNonce, User, WithdrawalRequest
from app.services import ledger

if TYPE_CHECKING:
    from app.chain.types import SenderClient

logger = logging.getLogger("kasa.worker.withdrawer")

_WITHDRAWAL_REF_TYPE = "withdrawal_request"
_DEFAULT_BATCH = 20


def _supports_skip_locked(session: AsyncSession) -> bool:
    try:
        return session.get_bind().dialect.name == "postgresql"
    except Exception:  # noqa: BLE001 - dialect probe is best-effort; default to no row locking
        return False


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
    if _supports_skip_locked(session):
        statement = statement.with_for_update(skip_locked=True)
    return list((await session.execute(statement)).scalars())


async def _nonce_row(
    session: AsyncSession,
    client: SenderClient,
    hot_wallet_address: str,
) -> HotWalletNonce:
    chain_id = client.chain_id
    statement: Select[tuple[HotWalletNonce]] = select(HotWalletNonce).where(
        HotWalletNonce.chain_id == chain_id,
    )
    if _supports_skip_locked(session):
        statement = statement.with_for_update()
    row = (await session.execute(statement)).scalar_one_or_none()
    if row is None:
        row = HotWalletNonce(
            chain_id=chain_id,
            address=hot_wallet_address,
            next_nonce=client.pending_nonce(hot_wallet_address),
        )
        session.add(row)
        await session.flush()
    return row


def _send(
    client: SenderClient,
    *,
    asset: Asset,
    request: WithdrawalRequest,
    private_key: str,
    nonce: int,
    gas_price: int,
) -> str:
    amount = int(request.amount)
    if asset.type == "native":
        return client.send_native(
            private_key=private_key,
            to_address=request.to_address,
            value=amount,
            nonce=nonce,
            gas_price=gas_price,
        )
    if asset.type == "erc20" and asset.contract_address is not None:
        return client.send_erc20(
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


async def broadcast_pending(
    session: AsyncSession,
    client: SenderClient,
    *,
    hot_wallet_key: str,
    hot_wallet_address: str,
    batch: int = _DEFAULT_BATCH,
) -> int:
    requests = await _claim_pending(session, client.chain_id, batch)
    if not requests:
        return 0
    nonce_row = await _nonce_row(session, client, hot_wallet_address)
    gas_price = client.suggested_gas_price()
    broadcast = 0
    for request in requests:
        nonce = nonce_row.next_nonce
        try:
            asset = await _load_asset(session, request.asset_id)
            request.attempts += 1
            tx_hash = _send(
                client,
                asset=asset,
                request=request,
                private_key=hot_wallet_key,
                nonce=nonce,
                gas_price=gas_price,
            )
        except (ChainRpcError, ValueError) as exc:
            # ChainRpcError from the client means the tx is *verified absent* (never broadcast);
            # ValueError means the asset is not withdrawable. Both are safe to refund.
            await _reverse_reservation(session, request, str(exc))
            continue
        except Exception:
            logger.exception(
                "withdrawal %s failed pre-broadcast on chain %s", request.id, client.chain_id,
            )
            continue
        request.tx_hash = tx_hash
        request.nonce = nonce
        request.status = WithdrawalStatus.BROADCAST.value
        nonce_row.next_nonce = nonce + 1
        broadcast += 1
    await session.flush()
    return broadcast


async def confirm_broadcast(
    session: AsyncSession,
    client: SenderClient,
    *,
    hot_wallet_address: str | None = None,
) -> int:
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
            await _reconcile_unmined(session, client, request, hot_wallet_address)
            continue
        if receipt.status == 1:
            await _settle(session, request)
            request.status = WithdrawalStatus.CONFIRMED.value
            settled += 1
        else:
            await _reverse_reservation(session, request, "transaction reverted on-chain")
    await session.flush()
    return settled


async def _reconcile_unmined(
    session: AsyncSession,
    client: SenderClient,
    request: WithdrawalRequest,
    hot_wallet_address: str | None,
) -> None:
    """A broadcast tx with no receipt: if the *mined* nonce has advanced past ours, our tx was
    dropped/replaced (a different tx filled the slot), so refund the reservation. Uses the mined
    (not pending) nonce so a still-pending tx is never wrongly reversed."""
    if hot_wallet_address is None or request.nonce is None:
        return
    if client.latest_nonce(hot_wallet_address) > request.nonce:
        await _reverse_reservation(session, request, "transaction dropped (nonce superseded)")
