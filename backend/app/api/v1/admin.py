from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from kasa_shared.registry import list_chains, native_asset
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_admin
from app.chain.client import ChainClient, ChainRpcError
from app.chain.types import BalanceClient
from app.core.config import Settings, get_settings
from app.core.enums import GasStatus
from app.core.hd_wallet import hot_wallet_account
from app.db import get_db
from app.models.tables import User
from app.schemas.admin import GasBalanceResponse, GasChainBalance, ReservesResponse
from app.schemas.nft import AdminMintNftRequest, AdminMintNftResponse
from app.schemas.withdrawal import WithdrawalPageResponse
from app.services import admin_service
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


def _gas_status(balance: int, settings: Settings) -> GasStatus:
    if balance < settings.gas_critical_wei:
        return GasStatus.CRITICAL
    if balance < settings.gas_warn_wei:
        return GasStatus.LOW
    return GasStatus.OK


@router.get("/reserves")
async def reserve_report(
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ReservesResponse:
    settings = get_settings()
    if not settings.reserves_onchain:
        return await admin_service.reserves(session)
    hot_wallet_address = hot_wallet_account(settings.master_mnemonic).address
    return await admin_service.reserves(
        session,
        hot_wallet_address=hot_wallet_address,
        balance_factory=_balance_factory(settings),
    )


@router.get("/gas")
async def gas_balances(
    _admin: Annotated[User, Depends(require_admin)],
) -> GasBalanceResponse:
    settings = get_settings()
    hot_wallet_address = hot_wallet_account(settings.master_mnemonic).address
    chains: list[GasChainBalance] = []
    for chain in list_chains():
        asset = native_asset(chain.chain_id)
        try:
            balance = ChainClient.from_settings(chain.chain_id, settings).native_balance(
                hot_wallet_address,
            )
            status = _gas_status(balance, settings)
        except ChainRpcError:
            balance = 0
            status = GasStatus.UNKNOWN
        chains.append(
            GasChainBalance(
                chain_id=chain.chain_id,
                symbol=asset.symbol,
                decimals=asset.decimals,
                balance=balance,
                status=status,
            ),
        )
    return GasBalanceResponse(chains=chains)


@router.get("/withdrawals")
async def admin_withdrawals(
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    cursor: Annotated[str | None, Query()] = None,
) -> WithdrawalPageResponse:
    limit = 50
    offset = _cursor_offset(cursor)
    rows = await admin_service.list_withdrawals(session, offset=offset, limit=limit + 1)
    next_cursor = str(offset + limit) if len(rows) > limit else None
    return WithdrawalPageResponse(
        items=[withdrawal_response(row) for row in rows[:limit]],
        next_cursor=next_cursor,
    )


@router.post("/mint-nft")
async def mint_nft(
    request: AdminMintNftRequest,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AdminMintNftResponse:
    settings = get_settings()
    onchain = settings.mint_onchain and bool(settings.master_mnemonic)
    # Custodial model: real mints go to the hot wallet so it can later sign the withdrawal transfer.
    hot_wallet_address = (
        hot_wallet_account(settings.master_mnemonic).address if onchain else None
    )
    response = await admin_service.mint_nft(
        session,
        admin_user_id=admin.id,
        user_email=request.user_email,
        chain_id=request.chain_id,
        onchain=onchain,
        hot_wallet_address=hot_wallet_address,
    )
    await session.commit()
    return response
