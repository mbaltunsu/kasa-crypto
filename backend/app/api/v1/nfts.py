from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import IdempotencyKey, get_current_user
from app.db import get_db
from app.models.tables import User
from app.schemas.nft import NftResponse, NftTransferCreateRequest, NftTransferCreateResponse
from app.services.nft_service import list_holdings, transfer_nft

router = APIRouter(tags=["nfts"])


@router.get("/nfts")
async def nfts(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[NftResponse]:
    return await list_holdings(session, user=user)


@router.post(
    "/nft-transfers",
    status_code=status.HTTP_201_CREATED,
)
async def nft_transfer(
    request: NftTransferCreateRequest,
    idempotency_key: IdempotencyKey,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> NftTransferCreateResponse:
    response = await transfer_nft(
        session,
        sender=user,
        to_email=request.to_email,
        nft_id=request.nft_id,
        idempotency_key=idempotency_key,
    )
    await session.commit()
    return response
