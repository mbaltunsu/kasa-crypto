from __future__ import annotations

from http import HTTPStatus
from uuid import UUID

from kasa_shared.registry import explorer_tx_url
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.addresses import InvalidAddressError, to_checksum_address_strict
from app.core.enums import ErrorCode, LedgerEntryType, WithdrawalStatus
from app.models.tables import User, WithdrawalRequest
from app.schemas.withdrawal import WithdrawalCreateResponse, WithdrawalResponse
from app.services import ledger
from app.services.errors import raise_api_error, raise_not_found
from app.services.idempotency import scoped_idempotency_key
from app.services.rate_limit import enforce_rate_limit
from app.services.wallet_service import get_asset


async def create_withdrawal(
    session: AsyncSession,
    *,
    user: User,
    asset_id: UUID,
    to_address: str,
    amount: int,
    idempotency_key: str,
) -> WithdrawalCreateResponse:
    await enforce_rate_limit(session, action="withdrawal", user_id=user.id)
    if amount <= 0:
        raise_api_error(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            ErrorCode.VALIDATION_ERROR,
            "Amount must be positive",
        )

    # Validate + canonicalize the destination at request time (before reserving funds) so a typo'd
    # checksum or the zero address can never be signed and broadcast (finding #14).
    try:
        to_address = to_checksum_address_strict(to_address)
    except InvalidAddressError as exc:
        raise_api_error(HTTPStatus.UNPROCESSABLE_ENTITY, ErrorCode.VALIDATION_ERROR, str(exc))

    scoped_key = scoped_idempotency_key(
        domain="withdraw", user_id=user.id, client_key=idempotency_key,
    )
    existing_tx = await ledger.find_transaction_by_idempotency_key(session, scoped_key)
    if existing_tx is not None and existing_tx.ref_type == "withdrawal_request":
        existing = await get_withdrawal_for_user(
            session,
            user=user,
            withdrawal_id=UUID(existing_tx.ref_id),
        )
        return WithdrawalCreateResponse(id=existing.id, status=WithdrawalStatus(existing.status))

    asset = await get_asset(session, asset_id)
    # Lock the user's wallet account before the balance check so two concurrent debits cannot both
    # pass and overspend (finding #2). Lock + read + post stay in this one transaction.
    await ledger.lock_user_asset(session, user=user, asset=asset)
    available = await ledger.available_balance(session, user=user, asset=asset)
    if available < amount:
        raise_api_error(HTTPStatus.BAD_REQUEST, ErrorCode.INSUFFICIENT_FUNDS, "Insufficient funds")

    withdrawal = WithdrawalRequest(
        user_id=user.id,
        asset_id=asset.id,
        chain_id=asset.chain_id,
        to_address=to_address,
        amount=amount,
        status=WithdrawalStatus.REQUESTED.value,
    )
    session.add(withdrawal)
    await session.flush()

    user_account = await ledger.get_user_wallet_account(session, user=user, asset=asset)
    reserve_account = await ledger.get_or_create_account(
        session,
        asset=asset,
        name=ledger.WITHDRAWALS_RESERVED_ACCOUNT,
        owner_type="system",
    )
    await ledger.post(
        session,
        transaction_type=LedgerEntryType.WITHDRAWAL,
        idempotency_key=scoped_key,
        ref_type="withdrawal_request",
        ref_id=str(withdrawal.id),
        legs=[
            ledger.LedgerLeg(user_account, asset, -amount),
            ledger.LedgerLeg(reserve_account, asset, amount),
        ],
    )
    return WithdrawalCreateResponse(id=withdrawal.id, status=WithdrawalStatus.REQUESTED)


async def get_withdrawal_for_user(
    session: AsyncSession,
    *,
    user: User,
    withdrawal_id: UUID,
) -> WithdrawalRequest:
    withdrawal = (
        await session.execute(
            select(WithdrawalRequest).where(
                WithdrawalRequest.id == withdrawal_id,
                WithdrawalRequest.user_id == user.id,
            ),
        )
    ).scalar_one_or_none()
    if withdrawal is None:
        raise_not_found("Withdrawal not found")
    return withdrawal


def withdrawal_response(withdrawal: WithdrawalRequest) -> WithdrawalResponse:
    explorer_url = (
        explorer_tx_url(withdrawal.chain_id, withdrawal.tx_hash)
        if withdrawal.tx_hash is not None
        else None
    )
    return WithdrawalResponse(
        id=withdrawal.id,
        asset_id=withdrawal.asset_id,
        chain_id=withdrawal.chain_id,
        to_address=withdrawal.to_address,
        amount=withdrawal.amount,
        status=WithdrawalStatus(withdrawal.status),
        tx_hash=withdrawal.tx_hash,
        explorer_url=explorer_url,
        created_at=withdrawal.created_at,
    )
