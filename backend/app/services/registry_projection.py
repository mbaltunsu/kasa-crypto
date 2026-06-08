from __future__ import annotations

import uuid
from typing import cast

from kasa_shared.models import Asset as RegistryAsset
from kasa_shared.models import Erc20Asset, Erc721Asset
from kasa_shared.registry import list_chains, tokens_of_chain

from app.schemas.registry import AssetResponse, ChainResponse

ASSET_NAMESPACE = uuid.UUID("c38a8b6f-7c61-4b83-9353-265a9e859c2f")


def asset_id_for(chain_id: int, asset: RegistryAsset) -> uuid.UUID:
    address = ""
    if asset.type.value != "native":
        address = cast(Erc20Asset | Erc721Asset, asset).address
    key = f"{chain_id}:{asset.type.value}:{asset.symbol.upper()}:{address.lower()}"
    return uuid.uuid5(ASSET_NAMESPACE, key)


def chain_responses() -> list[ChainResponse]:
    return [
        ChainResponse(
            chain_id=chain.chain_id,
            name=chain.name,
            symbol=chain.native_symbol,
            explorer_tx_url=chain.explorer_tx_url,
        )
        for chain in list_chains()
    ]


def asset_responses(chain_id: int | None = None) -> list[AssetResponse]:
    chains = [chain_id] if chain_id is not None else [chain.chain_id for chain in list_chains()]
    responses: list[AssetResponse] = []
    for current_chain_id in chains:
        for asset in tokens_of_chain(current_chain_id):
            contract_address = None
            if asset.type.value != "native":
                contract_address = cast(Erc20Asset | Erc721Asset, asset).address
            responses.append(
                AssetResponse(
                    id=asset_id_for(current_chain_id, asset),
                    chain_id=current_chain_id,
                    symbol=asset.symbol.upper(),
                    type=asset.type.value,
                    contract_address=contract_address,
                    decimals=asset.decimals,
                ),
            )
    return responses
