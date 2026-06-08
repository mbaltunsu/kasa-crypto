from uuid import UUID

from pydantic import BaseModel

from app.core.enums import TransferStatus


class NftResponse(BaseModel):
    id: UUID
    chain_id: int
    contract: str
    token_id: str
    image: str
    explorer_url: str


class NftTransferCreateRequest(BaseModel):
    nft_id: UUID
    to_email: str


class NftTransferCreateResponse(BaseModel):
    id: UUID
    status: TransferStatus


class AdminMintNftRequest(BaseModel):
    user_email: str
    chain_id: int


class AdminMintNftResponse(BaseModel):
    tx_hash: str
    token_id: str
