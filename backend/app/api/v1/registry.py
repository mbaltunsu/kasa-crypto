from fastapi import APIRouter, Query

from app.core.enums import ErrorCode
from app.schemas.registry import AssetResponse, ChainResponse
from app.services.errors import raise_api_error
from app.services.registry_projection import asset_responses, chain_responses

router = APIRouter(tags=["registry"])


@router.get("/chains", response_model=list[ChainResponse])
async def chains() -> list[ChainResponse]:
    return chain_responses()


@router.get("/assets", response_model=list[AssetResponse])
async def assets(chain_id: int | None = Query(default=None)) -> list[AssetResponse]:
    try:
        return asset_responses(chain_id)
    except KeyError:
        raise_api_error(400, ErrorCode.UNSUPPORTED_CHAIN, "Unsupported chain")
