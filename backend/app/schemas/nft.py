from pydantic import BaseModel


class NftResponse(BaseModel):
    chain_id: int
    contract: str
    token_id: str
    explorer_url: str


class AdminMintNftRequest(BaseModel):
    user_email: str
    chain_id: int


class AdminMintNftResponse(BaseModel):
    tx_hash: str
    token_id: str
