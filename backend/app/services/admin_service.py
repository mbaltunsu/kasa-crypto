from __future__ import annotations

import hashlib
from http import HTTPStatus

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ErrorCode
from app.models.tables import Asset, LedgerAccount, LedgerEntry, User, WithdrawalRequest
from app.schemas.admin import ReserveAssetResponse, ReservesResponse
from app.schemas.nft import AdminMintNftResponse
from app.services.errors import raise_api_error


async def reserves(session: AsyncSession) -> ReservesResponse:
    assets = (await session.execute(select(Asset).order_by(Asset.chain_id, Asset.symbol))).scalars().all()
    rows: list[ReserveAssetResponse] = []
    for asset in assets:
        liabilities_statement = (
            select(func.coalesce(func.sum(LedgerEntry.amount), 0))
            .join(LedgerAccount, LedgerAccount.id == LedgerEntry.account_id)
            .where(
                LedgerAccount.owner_type == "user",
                LedgerAccount.name == "wallet",
                LedgerEntry.asset_id == asset.id,
            )
        )
        liabilities = max(0, int((await session.execute(liabilities_statement)).scalar_one()))
        # TODO(worker-slice): replace this with on-chain reads across hot wallet + deposit addresses.
        chain_reserves = liabilities
        rows.append(
            ReserveAssetResponse(
                asset_id=asset.id,
                liabilities=liabilities,
                reserves=chain_reserves,
                delta=chain_reserves - liabilities,
            ),
        )
    return ReservesResponse(assets=rows)


async def list_withdrawals(
    session: AsyncSession,
    *,
    offset: int,
    limit: int,
) -> list[WithdrawalRequest]:
    return list(
        (
            await session.execute(
                select(WithdrawalRequest)
                .order_by(WithdrawalRequest.created_at.desc(), WithdrawalRequest.id.desc())
                .offset(offset)
                .limit(limit),
            )
        ).scalars(),
    )


async def mint_nft_stub(
    session: AsyncSession,
    *,
    user_email: str,
    chain_id: int,
) -> AdminMintNftResponse:
    user = (
        await session.execute(select(User).where(User.email == user_email.strip().lower()))
    ).scalar_one_or_none()
    if user is None:
        raise_api_error(HTTPStatus.NOT_FOUND, ErrorCode.NOT_FOUND, "User not found")

    # TODO(worker-slice): submit an ERC-721 mint transaction to the user's deposit address.
    digest = hashlib.sha256(f"{user.id}:{chain_id}".encode("utf-8")).hexdigest()
    return AdminMintNftResponse(tx_hash="0x" + digest, token_id=str(int(digest[:12], 16)))
