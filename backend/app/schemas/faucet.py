from uuid import UUID

from pydantic import BaseModel

from app.core.enums import DepositStatus
from app.types.amount import UnsignedBaseUnit


class FaucetRequest(BaseModel):
    asset_id: UUID
    amount: UnsignedBaseUnit


class FaucetResponse(BaseModel):
    tx_hash: str
    status: DepositStatus
