from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.enums import DepositStatus
from app.db import get_db
from app.models.tables import Asset, OnchainDeposit, User
from app.schemas.deposit import DepositPageResponse, DepositResponse
from app.services.wallet_service import deposit_confirmations, deposit_explorer_url

router = APIRouter(prefix="/deposits", tags=["deposits"])


def _cursor_offset(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        return max(0, int(cursor))
    except ValueError:
        return 0


@router.get("", response_model=DepositPageResponse)
async def deposits(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    cursor: str | None = Query(default=None),
) -> DepositPageResponse:
    limit = 50
    offset = _cursor_offset(cursor)
    rows = list(
        (
            await session.execute(
                select(OnchainDeposit, Asset)
                .join(Asset, Asset.id == OnchainDeposit.asset_id)
                .where(OnchainDeposit.user_id == user.id)
                .order_by(OnchainDeposit.block_number.desc(), OnchainDeposit.id.desc())
                .offset(offset)
                .limit(limit + 1),
            )
        ).all(),
    )
    items: list[DepositResponse] = []
    for deposit, asset in rows[:limit]:
        items.append(
            DepositResponse(
                id=deposit.id,
                chain_id=deposit.chain_id,
                asset_id=deposit.asset_id,
                symbol=asset.symbol,
                amount=deposit.amount,
                status=DepositStatus(deposit.status),
                confirmations=deposit_confirmations(deposit),
                tx_hash=deposit.tx_hash,
                explorer_url=deposit_explorer_url(deposit),
                created_at=deposit.created_at,
            ),
        )
    next_cursor = str(offset + limit) if len(rows) > limit else None
    return DepositPageResponse(items=items, next_cursor=next_cursor)
