"""ERC-721 withdrawal outbox.

NFT withdrawals sign safeTransferFrom FROM THE HOT WALLET, mirroring fungible withdrawals
that pay from the custody hot wallet regardless of which deposit address received funds. The
on-chain sweep is the same documented abstraction already used by this codebase. Mints,
fungible withdrawals, and NFT withdrawals all serialize on the shared `hot_wallet_nonces` row.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import Select, select

from app.chain.client import ChainRpcError
from app.core.enums import NftHoldingStatus, NftWithdrawalStatus
from app.models.tables import NftHolding, NftWithdrawalRequest
from worker._nonce import nonce_row, supports_skip_locked

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.chain.types import SenderClient

logger = logging.getLogger("kasa.worker.nft_withdrawer")

_DEFAULT_BATCH = 20


async def _claim_pending_withdrawals(
    session: AsyncSession,
    chain_id: int,
    batch: int,
) -> list[NftWithdrawalRequest]:
    statement: Select[tuple[NftWithdrawalRequest]] = (
        select(NftWithdrawalRequest)
        .where(
            NftWithdrawalRequest.chain_id == chain_id,
            NftWithdrawalRequest.status.in_(
                [NftWithdrawalStatus.REQUESTED.value, NftWithdrawalStatus.APPROVED.value],
            ),
        )
        .order_by(NftWithdrawalRequest.created_at, NftWithdrawalRequest.id)
        .limit(batch)
    )
    if supports_skip_locked(session):
        statement = statement.with_for_update(skip_locked=True)
    return list((await session.execute(statement)).scalars())


async def sign_pending_withdrawals(
    session: AsyncSession,
    client: SenderClient,
    *,
    hot_wallet_key: str,
    hot_wallet_address: str,
    batch: int = _DEFAULT_BATCH,
) -> int:
    requests = await _claim_pending_withdrawals(session, client.chain_id, batch)
    if not requests:
        return 0
    hot_nonce = await nonce_row(session, client, hot_wallet_address)
    gas_price = client.suggested_gas_price()
    signed = 0
    for request in requests:
        nonce = hot_nonce.next_nonce
        try:
            request.attempts += 1
            tx = client.sign_erc721_transfer(
                private_key=hot_wallet_key,
                contract_address=request.contract,
                from_address=hot_wallet_address,
                to_address=request.to_address,
                token_id=request.token_id,
                nonce=nonce,
                gas_price=gas_price,
            )
        except Exception:
            logger.exception(
                "nft withdrawal %s failed pre-sign on chain %s",
                request.id,
                client.chain_id,
            )
            continue
        request.signed_tx = tx.raw
        request.tx_hash = tx.tx_hash
        request.nonce = nonce
        request.status = NftWithdrawalStatus.SIGNING.value
        hot_nonce.next_nonce = nonce + 1
        signed += 1
    await session.flush()
    return signed


async def broadcast_signed_withdrawals(session: AsyncSession, client: SenderClient) -> int:
    requests = list(
        (
            await session.execute(
                select(NftWithdrawalRequest)
                .where(
                    NftWithdrawalRequest.chain_id == client.chain_id,
                    NftWithdrawalRequest.status == NftWithdrawalStatus.SIGNING.value,
                )
                .order_by(NftWithdrawalRequest.nonce),
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
            logger.warning("nft withdrawal %s broadcast failed; will retry next pass", request.id)
            continue
        request.status = NftWithdrawalStatus.BROADCAST.value
        broadcast += 1
    await session.flush()
    return broadcast


async def broadcast_pending_withdrawals(
    session: AsyncSession,
    client: SenderClient,
    *,
    hot_wallet_key: str,
    hot_wallet_address: str,
    batch: int = _DEFAULT_BATCH,
) -> int:
    await sign_pending_withdrawals(
        session,
        client,
        hot_wallet_key=hot_wallet_key,
        hot_wallet_address=hot_wallet_address,
        batch=batch,
    )
    return await broadcast_signed_withdrawals(session, client)


async def confirm_withdrawals(
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
                select(NftWithdrawalRequest).where(
                    NftWithdrawalRequest.chain_id == client.chain_id,
                    NftWithdrawalRequest.status == NftWithdrawalStatus.BROADCAST.value,
                ),
            )
        ).scalars(),
    )
    confirmed = 0
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
        if head - receipt.block_number < confirmations:
            continue
        canonical = client.block_hash(receipt.block_number)
        if canonical is None or canonical != receipt.block_hash:
            continue
        if receipt.status == 1:
            await _mark_withdrawn(session, request)
            request.status = NftWithdrawalStatus.CONFIRMED.value
            confirmed += 1
        else:
            await _fail_and_release(session, request, "transaction reverted on-chain")
    await session.flush()
    return confirmed


async def _mark_withdrawn(session: AsyncSession, request: NftWithdrawalRequest) -> None:
    holding = await session.get(NftHolding, request.nft_holding_id)
    if holding is not None:
        holding.status = NftHoldingStatus.WITHDRAWN.value


async def _fail_and_release(
    session: AsyncSession,
    request: NftWithdrawalRequest,
    error: str,
) -> None:
    holding = await session.get(NftHolding, request.nft_holding_id)
    if holding is not None:
        holding.status = NftHoldingStatus.HELD.value
    request.status = NftWithdrawalStatus.FAILED.value
    request.error = error


async def _reconcile_unmined(  # noqa: PLR0913
    session: AsyncSession,
    client: SenderClient,
    request: NftWithdrawalRequest,
    hot_wallet_address: str | None,
    *,
    head: int,
    confirmations: int,
) -> None:
    """Mark a receipt-absent tx dropped only after nonce advancement persists for confirmations."""
    if hot_wallet_address is None or request.nonce is None:
        return
    if client.latest_nonce(hot_wallet_address) <= request.nonce:
        request.unmined_since_block = None
        return
    if request.unmined_since_block is None:
        request.unmined_since_block = head
        return
    if head - request.unmined_since_block >= confirmations:
        await _fail_and_release(session, request, "transaction dropped (nonce superseded)")
