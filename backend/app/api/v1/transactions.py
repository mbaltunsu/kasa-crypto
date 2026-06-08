from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.enums import LedgerEntryType
from app.db import get_db
from app.models.tables import Asset, LedgerAccount, LedgerEntry, LedgerTransaction, User
from app.schemas.ledger import LedgerTxPageResponse, LedgerTxResponse

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _cursor_offset(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        return max(0, int(cursor))
    except ValueError:
        return 0


def _entry_type(transaction_type: str, amount: int) -> LedgerEntryType:
    if transaction_type == LedgerEntryType.TRANSFER_OUT.value and amount > 0:
        return LedgerEntryType.TRANSFER_IN
    return LedgerEntryType(transaction_type)


@router.get("", response_model=LedgerTxPageResponse)
async def transactions(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    asset_id: UUID | None = Query(default=None),
    cursor: str | None = Query(default=None),
) -> LedgerTxPageResponse:
    limit = 50
    offset = _cursor_offset(cursor)
    statement = (
        select(LedgerEntry, LedgerTransaction, Asset)
        .join(LedgerAccount, LedgerAccount.id == LedgerEntry.account_id)
        .join(LedgerTransaction, LedgerTransaction.id == LedgerEntry.transaction_id)
        .join(Asset, Asset.id == LedgerEntry.asset_id)
        .where(
            LedgerAccount.owner_type == "user",
            LedgerAccount.user_id == user.id,
            LedgerAccount.name == "wallet",
        )
        .order_by(LedgerTransaction.created_at.desc(), LedgerTransaction.id.desc())
        .offset(offset)
        .limit(limit + 1)
    )
    if asset_id is not None:
        statement = statement.where(LedgerEntry.asset_id == asset_id)
    rows = list((await session.execute(statement)).all())
    items = [
        LedgerTxResponse(
            id=transaction.id,
            type=_entry_type(transaction.type, int(entry.amount)),
            asset_id=asset.id,
            symbol=asset.symbol,
            amount=int(entry.amount),
            ref=f"{transaction.ref_type}:{transaction.ref_id}",
            created_at=transaction.created_at,
        )
        for entry, transaction, asset in rows[:limit]
    ]
    next_cursor = str(offset + limit) if len(rows) > limit else None
    return LedgerTxPageResponse(items=items, next_cursor=next_cursor)
