from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_admin
from app.chain.client import ChainClient
from app.chain.types import BalanceClient
from app.core.config import Settings, get_settings
from app.core.hd_wallet import hot_wallet_account
from app.db import get_db
from app.models.tables import User
from app.schemas.admin import ReservesResponse
from app.schemas.nft import AdminMintNftRequest, AdminMintNftResponse
from app.schemas.withdrawal import WithdrawalPageResponse
from app.services.admin_service import list_withdrawals, mint_nft_stub, reserves
from app.services.withdrawal_service import withdrawal_response

router = APIRouter(prefix="/admin", tags=["admin"])


def _balance_factory(settings: Settings) -> Callable[[int], BalanceClient]:
    def make(chain_id: int) -> BalanceClient:
        return ChainClient.from_settings(chain_id, settings)

    return make


def _cursor_offset(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        return max(0, int(cursor))
    except ValueError:
        return 0


@router.get("/reserves")
async def reserve_report(
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ReservesResponse:
    settings = get_settings()
    if not settings.reserves_onchain:
        return await reserves(session)
    hot_wallet_address = hot_wallet_account(settings.master_mnemonic).address
    return await reserves(
        session,
        hot_wallet_address=hot_wallet_address,
        balance_factory=_balance_factory(settings),
    )


@router.get("/withdrawals")
async def admin_withdrawals(
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    cursor: Annotated[str | None, Query()] = None,
) -> WithdrawalPageResponse:
    limit = 50
    offset = _cursor_offset(cursor)
    rows = await list_withdrawals(session, offset=offset, limit=limit + 1)
    next_cursor = str(offset + limit) if len(rows) > limit else None
    return WithdrawalPageResponse(
        items=[withdrawal_response(row) for row in rows[:limit]],
        next_cursor=next_cursor,
    )


@router.post("/mint-nft")
async def mint_nft(
    request: AdminMintNftRequest,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AdminMintNftResponse:
    response = await mint_nft_stub(
        session,
        user_email=request.user_email,
        chain_id=request.chain_id,
    )
    await session.commit()
    return response
