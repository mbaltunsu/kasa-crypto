from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.core.enums import DepositStatus
from app.types.amount import UnsignedBaseUnit


class DepositResponse(BaseModel):
    id: UUID
    chain_id: int
    asset_id: UUID
    symbol: str
    amount: UnsignedBaseUnit
    status: DepositStatus
    confirmations: int
    tx_hash: str
    explorer_url: str
    created_at: datetime


class DepositPageResponse(BaseModel):
    items: list[DepositResponse]
    next_cursor: str | None
