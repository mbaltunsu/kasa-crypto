from uuid import UUID

from pydantic import BaseModel, Field

from app.core.enums import TransferStatus
from app.types.amount import UnsignedBaseUnit


class TransferCreateRequest(BaseModel):
    to_email: str = Field(min_length=3, max_length=320)
    asset_id: UUID
    amount: UnsignedBaseUnit


class TransferCreateResponse(BaseModel):
    id: UUID
    status: TransferStatus
