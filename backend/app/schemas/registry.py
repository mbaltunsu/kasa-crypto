from uuid import UUID

from pydantic import BaseModel

from app.core.enums import AssetType


class ChainResponse(BaseModel):
    chain_id: int
    name: str
    symbol: str
    explorer_tx_url: str


class AssetResponse(BaseModel):
    id: UUID
    chain_id: int
    symbol: str
    type: AssetType
    contract_address: str | None
    decimals: int
