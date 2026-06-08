from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db import get_db
from app.models.tables import User
from app.schemas.nft import NftResponse

router = APIRouter(prefix="/nfts", tags=["nfts"])


@router.get("", response_model=list[NftResponse])
async def nfts(
    _user: Annotated[User, Depends(get_current_user)],
    _session: Annotated[AsyncSession, Depends(get_db)],
) -> list[NftResponse]:
    # TODO(worker-slice): read ERC-721 ownership from chain/indexer.
    return []
