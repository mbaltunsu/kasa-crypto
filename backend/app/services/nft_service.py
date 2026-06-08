from __future__ import annotations

from http import HTTPStatus
from importlib import import_module
from typing import TYPE_CHECKING, cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.addresses import InvalidAddressError, to_checksum_address_strict
from app.core.enums import ErrorCode, NftHoldingStatus, NftWithdrawalStatus, TransferStatus
from app.models.tables import NftHolding, NftTransfer, NftWithdrawalRequest, User
from app.schemas.nft import (
    NftResponse,
    NftTransferCreateResponse,
    NftWithdrawalCreateResponse,
)
from app.services import nft_art
from app.services.errors import raise_api_error
from app.services.idempotency import scoped_idempotency_key

if TYPE_CHECKING:
    from typing import Protocol
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    class _RegistryModule(Protocol):
        def explorer_address_url(self, chain_id: int, address: str) -> str: ...


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _explorer_address_url(chain_id: int, address: str) -> str:
    registry = cast("_RegistryModule", import_module("kasa_shared.registry"))
    return registry.explorer_address_url(chain_id, address)


async def list_holdings(session: AsyncSession, *, user: User) -> list[NftResponse]:
    holdings = (
        (
            await session.execute(
                select(NftHolding)
                .where(
                    NftHolding.user_id == user.id,
                    NftHolding.status == NftHoldingStatus.HELD.value,
                )
                .order_by(NftHolding.acquired_at.desc(), NftHolding.id.desc()),
            )
        )
        .scalars()
        .all()
    )
    return [_holding_response(holding) for holding in holdings]


async def transfer_nft(
    session: AsyncSession,
    *,
    sender: User,
    to_email: str,
    nft_id: UUID,
    idempotency_key: str,
) -> NftTransferCreateResponse:
    scoped_key = scoped_idempotency_key(
        domain="nft-transfer", user_id=sender.id, client_key=idempotency_key,
    )
    existing_transfer = await _find_transfer_by_idempotency_key(session, scoped_key)
    if existing_transfer is not None:
        return NftTransferCreateResponse(
            id=existing_transfer.id,
            status=TransferStatus(existing_transfer.status),
        )

    recipient = (
        await session.execute(select(User).where(User.email == _normalize_email(to_email)))
    ).scalar_one_or_none()
    if recipient is None:
        raise_api_error(HTTPStatus.NOT_FOUND, ErrorCode.NOT_FOUND, "Recipient not found")
    if recipient.id == sender.id:
        raise_api_error(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            ErrorCode.VALIDATION_ERROR,
            "Cannot transfer to yourself",
        )

    holding = (
        await session.execute(
            select(NftHolding)
            .where(
                NftHolding.id == nft_id,
                NftHolding.user_id == sender.id,
                NftHolding.status == NftHoldingStatus.HELD.value,
            )
            .with_for_update(),
        )
    ).scalar_one_or_none()
    if holding is None:
        existing_transfer = await _find_transfer_by_idempotency_key(session, scoped_key)
        if existing_transfer is not None:
            return NftTransferCreateResponse(
                id=existing_transfer.id,
                status=TransferStatus(existing_transfer.status),
            )
        raise_api_error(HTTPStatus.NOT_FOUND, ErrorCode.NOT_FOUND, "NFT not found")

    holding.user_id = recipient.id
    transfer = NftTransfer(
        nft_holding_id=holding.id,
        sender_user_id=sender.id,
        recipient_user_id=recipient.id,
        status=TransferStatus.CONFIRMED.value,
        idempotency_key=scoped_key,
    )
    session.add(transfer)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        existing_transfer = await _find_transfer_by_idempotency_key(session, scoped_key)
        if existing_transfer is not None:
            return NftTransferCreateResponse(
                id=existing_transfer.id,
                status=TransferStatus(existing_transfer.status),
            )
        raise
    return NftTransferCreateResponse(id=transfer.id, status=TransferStatus.CONFIRMED)


async def request_withdrawal(
    session: AsyncSession,
    *,
    user: User,
    nft_id: UUID,
    to_address: str,
    idempotency_key: str,
) -> NftWithdrawalCreateResponse:
    try:
        to_address = to_checksum_address_strict(to_address)
    except InvalidAddressError as exc:
        raise_api_error(HTTPStatus.UNPROCESSABLE_ENTITY, ErrorCode.VALIDATION_ERROR, str(exc))

    scoped_key = scoped_idempotency_key(
        domain="nft-withdrawal", user_id=user.id, client_key=idempotency_key,
    )
    existing_withdrawal = await _find_withdrawal_by_idempotency_key(session, scoped_key)
    if existing_withdrawal is not None:
        return NftWithdrawalCreateResponse(
            id=existing_withdrawal.id,
            status=NftWithdrawalStatus(existing_withdrawal.status),
        )

    holding = (
        await session.execute(
            select(NftHolding)
            .where(
                NftHolding.id == nft_id,
                NftHolding.user_id == user.id,
                NftHolding.status == NftHoldingStatus.HELD.value,
            )
            .with_for_update(),
        )
    ).scalar_one_or_none()
    if holding is None:
        existing_withdrawal = await _find_withdrawal_by_idempotency_key(session, scoped_key)
        if existing_withdrawal is not None:
            return NftWithdrawalCreateResponse(
                id=existing_withdrawal.id,
                status=NftWithdrawalStatus(existing_withdrawal.status),
            )
        raise_api_error(HTTPStatus.NOT_FOUND, ErrorCode.NOT_FOUND, "NFT not found")

    holding.status = NftHoldingStatus.WITHDRAWING.value
    withdrawal = NftWithdrawalRequest(
        user_id=user.id,
        nft_holding_id=holding.id,
        chain_id=holding.chain_id,
        contract=holding.contract,
        token_id=holding.token_id,
        to_address=to_address,
        status=NftWithdrawalStatus.REQUESTED.value,
        idempotency_key=scoped_key,
    )
    session.add(withdrawal)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        existing_withdrawal = await _find_withdrawal_by_idempotency_key(session, scoped_key)
        if existing_withdrawal is not None:
            return NftWithdrawalCreateResponse(
                id=existing_withdrawal.id,
                status=NftWithdrawalStatus(existing_withdrawal.status),
            )
        raise
    return NftWithdrawalCreateResponse(id=withdrawal.id, status=NftWithdrawalStatus.REQUESTED)


async def _find_transfer_by_idempotency_key(
    session: AsyncSession,
    idempotency_key: str,
) -> NftTransfer | None:
    return (
        await session.execute(
            select(NftTransfer).where(NftTransfer.idempotency_key == idempotency_key),
        )
    ).scalar_one_or_none()


async def _find_withdrawal_by_idempotency_key(
    session: AsyncSession,
    idempotency_key: str,
) -> NftWithdrawalRequest | None:
    return (
        await session.execute(
            select(NftWithdrawalRequest).where(
                NftWithdrawalRequest.idempotency_key == idempotency_key,
            ),
        )
    ).scalar_one_or_none()


def _holding_response(holding: NftHolding) -> NftResponse:
    return NftResponse(
        id=holding.id,
        chain_id=holding.chain_id,
        contract=holding.contract,
        token_id=holding.token_id,
        image=nft_art.data_uri(holding.chain_id, holding.contract, holding.token_id),
        explorer_url=_explorer_address_url(holding.chain_id, holding.contract),
    )
