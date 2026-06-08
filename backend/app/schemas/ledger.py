from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.core.enums import LedgerEntryType
from app.types.amount import BaseUnit


class LedgerTxResponse(BaseModel):
    id: UUID
    type: LedgerEntryType
    asset_id: UUID
    symbol: str
    amount: BaseUnit
    ref: str
    created_at: datetime


class LedgerTxPageResponse(BaseModel):
    items: list[LedgerTxResponse]
    next_cursor: str | None
