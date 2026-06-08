from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import IdempotencyKey, get_current_user
from app.db import get_db
from app.models.tables import User
from app.schemas.transfer import TransferCreateRequest, TransferCreateResponse
from app.services.transfer_service import create_transfer

router = APIRouter(prefix="/transfers", tags=["transfers"])


@router.post("", response_model=TransferCreateResponse, status_code=status.HTTP_201_CREATED)
async def transfer(
    request: TransferCreateRequest,
    idempotency_key: IdempotencyKey,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TransferCreateResponse:
    response = await create_transfer(
        session,
        sender=user,
        to_email=request.to_email,
        asset_id=request.asset_id,
        amount=request.amount,
        idempotency_key=idempotency_key,
    )
    await session.commit()
    return response
