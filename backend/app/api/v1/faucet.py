from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import IdempotencyKey, get_current_user
from app.db import get_db
from app.models.tables import User
from app.schemas.faucet import FaucetRequest, FaucetResponse
from app.services.wallet_service import request_faucet

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/faucet", response_model=FaucetResponse)
async def faucet(
    request: FaucetRequest,
    idempotency_key: IdempotencyKey,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FaucetResponse:
    response = await request_faucet(
        session,
        user=user,
        asset_id=request.asset_id,
        amount=request.amount,
        idempotency_key=idempotency_key,
    )
    await session.commit()
    return response
