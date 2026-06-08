from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db import get_db
from app.models.tables import User
from app.schemas.wallet import BalanceResponse, DepositAddressResponse
from app.services.wallet_service import list_balances, list_deposit_addresses

router = APIRouter(prefix="/wallet", tags=["wallet"])


@router.get("/deposit-addresses", response_model=list[DepositAddressResponse])
async def deposit_addresses(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[DepositAddressResponse]:
    return await list_deposit_addresses(session, user=user)


@router.get("/balances", response_model=list[BalanceResponse])
async def balances(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[BalanceResponse]:
    return await list_balances(session, user=user)
