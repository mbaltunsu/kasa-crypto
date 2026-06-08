from __future__ import annotations

from http import HTTPStatus
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ErrorCode, LedgerEntryType, TransferStatus
from app.models.tables import User
from app.schemas.transfer import TransferCreateResponse
from app.services import ledger
from app.services.errors import raise_api_error
from app.services.wallet_service import get_asset


def _normalize_email(email: str) -> str:
    return email.strip().lower()


async def create_transfer(
    session: AsyncSession,
    *,
    sender: User,
    to_email: str,
    asset_id: UUID,
    amount: int,
    idempotency_key: str,
) -> TransferCreateResponse:
    if amount <= 0:
        raise_api_error(HTTPStatus.UNPROCESSABLE_ENTITY, ErrorCode.VALIDATION_ERROR, "Amount must be positive")

    existing_tx = await ledger.find_transaction_by_idempotency_key(session, idempotency_key)
    if existing_tx is not None:
        return TransferCreateResponse(id=existing_tx.id, status=TransferStatus.CONFIRMED)

    recipient = (
        await session.execute(select(User).where(User.email == _normalize_email(to_email)))
    ).scalar_one_or_none()
    if recipient is None:
        raise_api_error(HTTPStatus.NOT_FOUND, ErrorCode.NOT_FOUND, "Recipient not found")
    if recipient.id == sender.id:
        raise_api_error(HTTPStatus.UNPROCESSABLE_ENTITY, ErrorCode.VALIDATION_ERROR, "Cannot transfer to yourself")

    asset = await get_asset(session, asset_id)
    available = await ledger.available_balance(session, user=sender, asset=asset)
    if available < amount:
        raise_api_error(HTTPStatus.BAD_REQUEST, ErrorCode.INSUFFICIENT_FUNDS, "Insufficient funds")

    sender_account = await ledger.get_user_wallet_account(session, user=sender, asset=asset)
    recipient_account = await ledger.get_user_wallet_account(session, user=recipient, asset=asset)
    transaction = await ledger.post(
        session,
        transaction_type=LedgerEntryType.TRANSFER_OUT,
        idempotency_key=idempotency_key,
        ref_type="internal_transfer",
        ref_id=f"{sender.id}:{recipient.id}",
        legs=[
            ledger.LedgerLeg(sender_account, asset, -amount),
            ledger.LedgerLeg(recipient_account, asset, amount),
        ],
    )
    return TransferCreateResponse(id=transaction.id, status=TransferStatus.CONFIRMED)
