from uuid import UUID

from pydantic import BaseModel

from app.types.amount import BaseUnit, UnsignedBaseUnit


class ReserveAssetResponse(BaseModel):
    asset_id: UUID
    liabilities: UnsignedBaseUnit
    reserves: UnsignedBaseUnit
    delta: BaseUnit


class ReservesResponse(BaseModel):
    assets: list[ReserveAssetResponse]
