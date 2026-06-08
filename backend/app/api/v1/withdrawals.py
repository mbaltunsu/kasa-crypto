from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import IdempotencyKey, get_current_user
from app.db import get_db
from app.models.tables import User, WithdrawalRequest
from app.schemas.withdrawal import (
    WithdrawalCreateRequest,
    WithdrawalCreateResponse,
    WithdrawalPageResponse,
    WithdrawalResponse,
)
from app.services.withdrawal_service import (
    create_withdrawal,
    get_withdrawal_for_user,
    withdrawal_response,
)

router = APIRouter(prefix="/withdrawals", tags=["withdrawals"])


def _cursor_offset(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        return max(0, int(cursor))
    except ValueError:
        return 0


@router.post("", response_model=WithdrawalCreateResponse, status_code=status.HTTP_201_CREATED)
async def create(
    request: WithdrawalCreateRequest,
    idempotency_key: IdempotencyKey,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WithdrawalCreateResponse:
    response = await create_withdrawal(
        session,
        user=user,
        asset_id=request.asset_id,
        to_address=request.to_address,
        amount=request.amount,
        idempotency_key=idempotency_key,
    )
    await session.commit()
    return response


@router.get("/{withdrawal_id}", response_model=WithdrawalResponse)
async def get_withdrawal(
    withdrawal_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WithdrawalResponse:
    withdrawal = await get_withdrawal_for_user(session, user=user, withdrawal_id=withdrawal_id)
    return withdrawal_response(withdrawal)


@router.get("", response_model=WithdrawalPageResponse)
async def list_user_withdrawals(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    cursor: str | None = Query(default=None),
) -> WithdrawalPageResponse:
    limit = 50
    offset = _cursor_offset(cursor)
    rows = list(
        (
            await session.execute(
                select(WithdrawalRequest)
                .where(WithdrawalRequest.user_id == user.id)
                .order_by(WithdrawalRequest.created_at.desc(), WithdrawalRequest.id.desc())
                .offset(offset)
                .limit(limit + 1),
            )
        ).scalars(),
    )
    next_cursor = str(offset + limit) if len(rows) > limit else None
    return WithdrawalPageResponse(
        items=[withdrawal_response(row) for row in rows[:limit]],
        next_cursor=next_cursor,
    )
