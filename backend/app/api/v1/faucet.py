from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import IdempotencyKey, get_current_user
from app.chain.client import ChainClient
from app.chain.types import SenderClient
from app.core.config import Settings, get_settings
from app.db import get_db
from app.models.tables import User
from app.schemas.faucet import FaucetRequest, FaucetResponse
from app.services.wallet_service import request_faucet

router = APIRouter(prefix="/demo", tags=["demo"])


def _sender_factory(settings: Settings) -> Callable[[int], SenderClient]:
    def make(chain_id: int) -> SenderClient:
        return ChainClient.from_settings(chain_id, settings)

    return make


@router.post("/faucet", response_model=FaucetResponse)
async def faucet(
    request: FaucetRequest,
    idempotency_key: IdempotencyKey,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FaucetResponse:
    settings = get_settings()
    sender_factory = _sender_factory(settings) if settings.faucet_private_key else None
    response = await request_faucet(
        session,
        user=user,
        asset_id=request.asset_id,
        amount=request.amount,
        idempotency_key=idempotency_key,
        faucet_private_key=settings.faucet_private_key,
        sender_factory=sender_factory,
    )
    await session.commit()
    return response
