from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from kasa_shared.registry import list_chains, tokens_of_chain

from app.core.config import get_settings
from app.schemas.registry import AssetResponse, ChainResponse
from app.services.limits import max_amount_base_units


def active_chain_ids() -> list[int]:
    """Registry chain ids minus any disabled by config (e.g. the local Hardhat chain in cloud)."""
    settings = get_settings()
    return [c.chain_id for c in list_chains() if settings.is_chain_enabled(c.chain_id)]

if TYPE_CHECKING:
    from kasa_shared.consts import AssetType
    from kasa_shared.models import Asset as RegistryAsset
    from kasa_shared.models import Erc20Asset, Erc721Asset

ASSET_NAMESPACE = uuid.UUID("c38a8b6f-7c61-4b83-9353-265a9e859c2f")


@dataclass(frozen=True)
class _RegistryProjectionAsset:
    chain_id: int
    symbol: str
    type: AssetType
    decimals: int


def asset_id_for(chain_id: int, asset: RegistryAsset) -> uuid.UUID:
    address = ""
    if asset.type.value != "native":
        address = cast("Erc20Asset | Erc721Asset", asset).address
    key = f"{chain_id}:{asset.type.value}:{asset.symbol.upper()}:{address.lower()}"
    return uuid.uuid5(ASSET_NAMESPACE, key)


def chain_responses() -> list[ChainResponse]:
    settings = get_settings()
    return [
        ChainResponse(
            chain_id=chain.chain_id,
            name=chain.name,
            symbol=chain.native_symbol,
            explorer_tx_url=chain.explorer_tx_url,
        )
        for chain in list_chains()
        if settings.is_chain_enabled(chain.chain_id)
    ]


def asset_responses(chain_id: int | None = None) -> list[AssetResponse]:
    settings = get_settings()
    chains = [chain_id] if chain_id is not None else active_chain_ids()
    chains = [cid for cid in chains if settings.is_chain_enabled(cid)]
    responses: list[AssetResponse] = []
    for current_chain_id in chains:
        for asset in tokens_of_chain(current_chain_id):
            contract_address = None
            if asset.type.value != "native":
                contract_address = cast("Erc20Asset | Erc721Asset", asset).address
            responses.append(
                AssetResponse(
                    id=asset_id_for(current_chain_id, asset),
                    chain_id=current_chain_id,
                    symbol=asset.symbol.upper(),
                    type=asset.type.value,
                    contract_address=contract_address,
                    decimals=asset.decimals,
                    max_amount=max_amount_base_units(
                        _RegistryProjectionAsset(
                            chain_id=current_chain_id,
                            symbol=asset.symbol,
                            type=asset.type,
                            decimals=asset.decimals,
                        ),
                    ),
                ),
            )
    return responses
