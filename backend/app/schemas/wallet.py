from uuid import UUID

from pydantic import BaseModel

from app.types.amount import UnsignedBaseUnit


class DepositAddressResponse(BaseModel):
    chain_id: int
    address: str


class BalanceResponse(BaseModel):
    asset_id: UUID
    chain_id: int
    symbol: str
    available: UnsignedBaseUnit
    pending: UnsignedBaseUnit
