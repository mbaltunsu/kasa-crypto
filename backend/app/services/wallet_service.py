from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from http import HTTPStatus
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import DepositStatus, ErrorCode, LedgerEntryType
from app.models.tables import Asset, DepositAddress, OnchainDeposit, User
from app.schemas.faucet import FaucetResponse
from app.schemas.wallet import BalanceResponse, DepositAddressResponse
from app.services import ledger
from app.services.errors import raise_api_error, raise_not_found
from kasa_shared.registry import explorer_tx_url, list_chains


async def get_asset(session: AsyncSession, asset_id: UUID) -> Asset:
    asset = (await session.execute(select(Asset).where(Asset.id == asset_id))).scalar_one_or_none()
    if asset is None:
        raise_api_error(HTTPStatus.NOT_FOUND, ErrorCode.UNKNOWN_ASSET, "Unknown asset")
    return asset


async def list_deposit_addresses(
    session: AsyncSession,
    *,
    user: User,
) -> list[DepositAddressResponse]:
    address = (
        await session.execute(select(DepositAddress).where(DepositAddress.user_id == user.id))
    ).scalar_one_or_none()
    if address is None:
        raise_not_found("Deposit address not found")
    return [
        DepositAddressResponse(chain_id=chain.chain_id, address=address.address)
        for chain in list_chains()
    ]


async def list_balances(session: AsyncSession, *, user: User) -> list[BalanceResponse]:
    assets = (await session.execute(select(Asset).order_by(Asset.chain_id, Asset.symbol))).scalars().all()
    responses: list[BalanceResponse] = []
    for asset in assets:
        available, pending = await ledger.balance(session, user=user, asset=asset)
        responses.append(
            BalanceResponse(
                asset_id=asset.id,
                chain_id=asset.chain_id,
                symbol=asset.symbol,
                available=max(0, available),
                pending=max(0, pending),
            ),
        )
    return responses


def _placeholder_tx_hash(idempotency_key: str) -> str:
    return "0x" + hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()


async def request_faucet(
    session: AsyncSession,
    *,
    user: User,
    asset_id: UUID,
    amount: int,
    idempotency_key: str,
) -> FaucetResponse:
    if amount <= 0:
        raise_api_error(HTTPStatus.UNPROCESSABLE_ENTITY, ErrorCode.VALIDATION_ERROR, "Amount must be positive")
    asset = await get_asset(session, asset_id)
    existing_tx = await ledger.find_transaction_by_idempotency_key(session, idempotency_key)
    if existing_tx is not None:
        tx_hash = existing_tx.ref_id
        return FaucetResponse(tx_hash=tx_hash, status=DepositStatus.SEEN)

    address = (
        await session.execute(select(DepositAddress).where(DepositAddress.user_id == user.id))
    ).scalar_one_or_none()
    if address is None:
        raise_not_found("Deposit address not found")

    tx_hash = _placeholder_tx_hash(idempotency_key)
    # TODO(worker-slice): replace this placeholder with a real faucet transaction sent from a
    # rate-limited funded key. Until then, the pending on-chain deposit lets the frontend integrate.
    session.add(
        OnchainDeposit(
            chain_id=asset.chain_id,
            tx_hash=tx_hash,
            log_index=0,
            block_number=0,
            block_hash="0x" + ("0" * 64),
            to_address=address.address,
            asset_id=asset.id,
            amount=amount,
            status=DepositStatus.SEEN.value,
            user_id=user.id,
        ),
    )
    await session.flush()

    source = await ledger.get_or_create_account(
        session,
        asset=asset,
        name="faucet_source",
        owner_type="system",
    )
    in_transit = await ledger.get_or_create_account(
        session,
        asset=asset,
        name="deposits_in_transit",
        owner_type="system",
    )
    await ledger.post(
        session,
        transaction_type=LedgerEntryType.DEPOSIT,
        idempotency_key=idempotency_key,
        ref_type="faucet_pending_tx",
        ref_id=tx_hash,
        legs=[
            ledger.LedgerLeg(source, asset, -amount),
            ledger.LedgerLeg(in_transit, asset, amount),
        ],
    )
    return FaucetResponse(tx_hash=tx_hash, status=DepositStatus.SEEN)


def deposit_confirmations(_deposit: OnchainDeposit) -> int:
    # TODO(worker-slice): compute confirmations from chain cursors/finalized block tracking.
    return 0


def deposit_explorer_url(deposit: OnchainDeposit) -> str:
    if deposit.tx_hash.startswith("0x") and len(deposit.tx_hash) == 66:
        return explorer_tx_url(deposit.chain_id, deposit.tx_hash)
    return ""


def now_utc() -> datetime:
    return datetime.now(UTC)
