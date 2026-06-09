"""ERC-721 mint outbox.

Mints spend from the same hot wallet as withdrawals, so nonce allocation must use the same
`hot_wallet_nonces` row lock. The HTTP admin path only enqueues requests; this worker signs,
broadcasts, and confirms them in separate durable phases.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import Select, func, select

from app.chain.client import ChainRpcError
from app.core.enums import NftHoldingStatus, NftMintStatus
from app.models.tables import NftHolding, NftMintRequest
from worker._nonce import nonce_row, supports_skip_locked

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.chain.types import SenderClient, SignedTx

logger = logging.getLogger("kasa.worker.nft_minter")

_DEFAULT_BATCH = 20


async def _claim_pending_mints(
    session: AsyncSession,
    chain_id: int,
    batch: int,
) -> list[NftMintRequest]:
    statement: Select[tuple[NftMintRequest]] = (
        select(NftMintRequest)
        .where(
            NftMintRequest.chain_id == chain_id,
            NftMintRequest.status == NftMintStatus.REQUESTED.value,
        )
        .order_by(NftMintRequest.created_at, NftMintRequest.id)
        .limit(batch)
    )
    if supports_skip_locked(session):
        statement = statement.with_for_update(skip_locked=True)
    return list((await session.execute(statement)).scalars())


def _sign(
    client: SenderClient,
    *,
    request: NftMintRequest,
    private_key: str,
    nonce: int,
    gas_price: int,
) -> SignedTx:
    return client.sign_erc721_mint(
        private_key=private_key,
        contract_address=request.contract,
        to_address=request.to_address,
        nonce=nonce,
        gas_price=gas_price,
    )


async def sign_pending_mints(
    session: AsyncSession,
    client: SenderClient,
    *,
    hot_wallet_key: str,
    hot_wallet_address: str,
    batch: int = _DEFAULT_BATCH,
) -> int:
    requests = await _claim_pending_mints(session, client.chain_id, batch)
    if not requests:
        return 0
    hot_nonce = await nonce_row(session, client, hot_wallet_address)
    gas_price = client.suggested_gas_price()
    signed = 0
    for request in requests:
        nonce = hot_nonce.next_nonce
        try:
            request.attempts += 1
            # DemoCollectible.mint is onlyOwner. The hot wallet at m/44'/60'/0'/0/0 must be the
            # contract owner on this chain, otherwise the transaction will revert on-chain.
            tx = _sign(
                client,
                request=request,
                private_key=hot_wallet_key,
                nonce=nonce,
                gas_price=gas_price,
            )
        except Exception:
            logger.exception("nft mint %s failed pre-sign on chain %s", request.id, client.chain_id)
            continue
        request.signed_tx = tx.raw
        request.tx_hash = tx.tx_hash
        request.nonce = nonce
        request.status = NftMintStatus.SIGNING.value
        hot_nonce.next_nonce = nonce + 1
        signed += 1
    await session.flush()
    return signed


async def broadcast_signed_mints(session: AsyncSession, client: SenderClient) -> int:
    requests = list(
        (
            await session.execute(
                select(NftMintRequest)
                .where(
                    NftMintRequest.chain_id == client.chain_id,
                    NftMintRequest.status == NftMintStatus.SIGNING.value,
                )
                .order_by(NftMintRequest.nonce),
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
            logger.warning("nft mint %s broadcast failed; will retry next pass", request.id)
            continue
        request.status = NftMintStatus.BROADCAST.value
        broadcast += 1
    await session.flush()
    return broadcast


async def broadcast_pending_mints(
    session: AsyncSession,
    client: SenderClient,
    *,
    hot_wallet_key: str,
    hot_wallet_address: str,
    batch: int = _DEFAULT_BATCH,
) -> int:
    await sign_pending_mints(
        session,
        client,
        hot_wallet_key=hot_wallet_key,
        hot_wallet_address=hot_wallet_address,
        batch=batch,
    )
    return await broadcast_signed_mints(session, client)


async def confirm_mints(
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
                select(NftMintRequest).where(
                    NftMintRequest.chain_id == client.chain_id,
                    NftMintRequest.status == NftMintStatus.BROADCAST.value,
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
        if receipt.status == 0:
            request.status = NftMintStatus.FAILED.value
            request.error = "transaction reverted on-chain"
            continue

        token_id = client.erc721_minted_token_id(
            tx_hash=request.tx_hash,
            contract_address=request.contract,
            to_address=request.to_address,
        )
        if token_id is None:
            request.status = NftMintStatus.FAILED.value
            request.error = "mint Transfer log missing"
            continue
        request.token_id = token_id
        await _record_holding(session, request, token_id)
        request.status = NftMintStatus.CONFIRMED.value
        confirmed += 1
    await session.flush()
    return confirmed


async def _record_holding(
    session: AsyncSession,
    request: NftMintRequest,
    token_id: str,
) -> None:
    existing = (
        await session.execute(
            select(NftHolding).where(
                NftHolding.chain_id == request.chain_id,
                func.lower(NftHolding.contract) == request.contract.lower(),
                NftHolding.token_id == token_id,
            ),
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.user_id = request.user_id
        existing.status = NftHoldingStatus.HELD.value
        return
    session.add(
        NftHolding(
            user_id=request.user_id,
            chain_id=request.chain_id,
            contract=request.contract,
            token_id=token_id,
            status=NftHoldingStatus.HELD.value,
        ),
    )


async def _reconcile_unmined(
    client: SenderClient,
    request: NftMintRequest,
    hot_wallet_address: str | None,
    *,
    head: int,
    confirmations: int,
) -> None:
    """Mark a receipt-absent mint dropped only after nonce advancement persists.

    A nonce advance can also mean a freshly mined tx whose receipt is lagging, so fail only
    after the receipt stays absent for the confirmation depth.
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
        request.status = NftMintStatus.FAILED.value
        request.error = "transaction dropped (nonce superseded)"
