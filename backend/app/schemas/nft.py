from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.core.enums import NftMintStatus, NftWithdrawalStatus, TransferStatus


class NftResponse(BaseModel):
    id: UUID
    chain_id: int
    contract: str
    token_id: str
    image: str
    explorer_url: str


class NftMintResponse(BaseModel):
    """A mint request in the user's collectible history. `tx_hash`/`explorer_url` are only set for
    real on-chain mints (offline-stub mints are simulated and carry no usable explorer link)."""

    id: UUID
    chain_id: int
    contract: str
    token_id: str | None = None
    status: NftMintStatus
    tx_hash: str | None = None
    explorer_url: str | None = None
    created_at: datetime


class NftTransferCreateRequest(BaseModel):
    nft_id: UUID
    to_email: str


class NftTransferCreateResponse(BaseModel):
    id: UUID
    status: TransferStatus


class NftWithdrawalCreateRequest(BaseModel):
    nft_id: UUID
    to_address: str


class NftWithdrawalCreateResponse(BaseModel):
    id: UUID
    status: NftWithdrawalStatus


class AdminMintNftRequest(BaseModel):
    user_email: str
    chain_id: int


class AdminMintNftResponse(BaseModel):
    request_id: UUID | None = None
    status: NftMintStatus
    tx_hash: str | None = None
    token_id: str | None = None
