from uuid import UUID

from pydantic import BaseModel

from app.core.enums import GasStatus
from app.types.amount import BaseUnit, UnsignedBaseUnit


class ReserveAssetResponse(BaseModel):
    asset_id: UUID
    liabilities: UnsignedBaseUnit
    reserves: UnsignedBaseUnit
    delta: BaseUnit


class ReservesResponse(BaseModel):
    assets: list[ReserveAssetResponse]


class GasChainBalance(BaseModel):
    chain_id: int
    symbol: str
    decimals: int
    balance: BaseUnit
    status: GasStatus


class GasBalanceResponse(BaseModel):
    chains: list[GasChainBalance]
