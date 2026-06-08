from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.enums import WithdrawalStatus
from app.types.amount import UnsignedBaseUnit


class WithdrawalCreateRequest(BaseModel):
    asset_id: UUID
    to_address: str = Field(min_length=1, max_length=128)
    amount: UnsignedBaseUnit


class WithdrawalCreateResponse(BaseModel):
    id: UUID
    status: WithdrawalStatus


class WithdrawalResponse(BaseModel):
    id: UUID
    asset_id: UUID
    chain_id: int
    to_address: str
    amount: UnsignedBaseUnit
    status: WithdrawalStatus
    tx_hash: str | None
    explorer_url: str | None
    created_at: datetime


class WithdrawalPageResponse(BaseModel):
    items: list[WithdrawalResponse]
    next_cursor: str | None
