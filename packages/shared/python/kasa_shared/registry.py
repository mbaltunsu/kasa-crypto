from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, TypeAlias, cast

from eth_utils import to_checksum_address
from pydantic import TypeAdapter

from kasa_shared.amounts import format_amount as _format_amount
from kasa_shared.amounts import parse_amount as _parse_amount
from kasa_shared.consts import AssetType, NATIVE_ASSET_SENTINEL, ZERO_ADDRESS
from kasa_shared.models import Asset, Chain, Erc20Asset, Erc721Asset, NativeAsset

AddressAsset: TypeAlias = Erc20Asset | Erc721Asset
_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_ZERO_LOOKUP = ZERO_ADDRESS.lower()
_NATIVE_SENTINEL_LOOKUP = NATIVE_ASSET_SENTINEL.lower()
_REGISTRY_ADAPTER = TypeAdapter(Chain)


@dataclass(frozen=True)
class Registry:
    chains: Mapping[int, Chain]
    by_symbol: Mapping[tuple[int, str], Asset]
    by_address: Mapping[tuple[int, str], AddressAsset]


def _data_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data"


def _read_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _checksum_asset(asset: Asset) -> Asset:
    if asset.type == AssetType.NATIVE:
        return asset
    data = asset.model_dump(by_alias=True)
    data["address"] = to_checksum_address(asset.address)
    if asset.type == AssetType.ERC20:
        return Erc20Asset.model_validate(data)
    return Erc721Asset.model_validate(data)


def _load_chain(path: Path) -> Chain:
    raw = _read_json(path)
    chain = _REGISTRY_ADAPTER.validate_python(raw)
    checksummed_assets = tuple(_checksum_asset(asset) for asset in chain.assets)
    return chain.model_copy(update={"assets": checksummed_assets})


@lru_cache(maxsize=1)
def load_registry() -> Registry:
    data_dir = _data_dir()
    manifest = _read_json(data_dir / "registry.json")
    chain_ids = manifest.get("chainIds")
    if not isinstance(chain_ids, list):
        msg = "registry manifest must contain chainIds"
        raise ValueError(msg)

    chains: dict[int, Chain] = {}
    by_symbol: dict[tuple[int, str], Asset] = {}
    by_address: dict[tuple[int, str], AddressAsset] = {}

    for raw_chain_id in chain_ids:
        if not isinstance(raw_chain_id, int):
            msg = "chainIds must be integers"
            raise ValueError(msg)
        chain = _load_chain(data_dir / "chains" / f"{raw_chain_id}.json")
        if chain.chain_id != raw_chain_id:
            msg = f"chain file {raw_chain_id} has mismatched chainId {chain.chain_id}"
            raise ValueError(msg)
        if chain.chain_id in chains:
            msg = f"duplicate chainId {chain.chain_id}"
            raise ValueError(msg)
        chains[chain.chain_id] = chain

        for asset in chain.assets:
            symbol_key = asset.symbol.upper()
            if symbol_key.startswith("0X"):
                msg = f"asset symbol must not be 0x-prefixed: {asset.symbol}"
                raise ValueError(msg)
            symbol_index_key = (chain.chain_id, symbol_key)
            if symbol_index_key in by_symbol:
                msg = f"duplicate symbol {asset.symbol} on chain {chain.chain_id}"
                raise ValueError(msg)
            by_symbol[symbol_index_key] = asset

            if asset.type != AssetType.NATIVE:
                address_asset = asset
                address_key = address_asset.address.lower()
                if address_key == _ZERO_LOOKUP:
                    continue
                address_index_key = (chain.chain_id, address_key)
                if address_index_key in by_address:
                    msg = f"duplicate address {address_asset.address} on chain {chain.chain_id}"
                    raise ValueError(msg)
                by_address[address_index_key] = address_asset

    return Registry(
        chains=MappingProxyType(chains),
        by_symbol=MappingProxyType(by_symbol),
        by_address=MappingProxyType(by_address),
    )


def get_chain(chain_id: int) -> Chain:
    chain = load_registry().chains.get(chain_id)
    if chain is None:
        msg = f"unsupported chain: {chain_id}"
        raise KeyError(msg)
    return chain


def list_chains() -> list[Chain]:
    return list(load_registry().chains.values())


def tokens_of_chain(chain_id: int) -> list[Asset]:
    return list(get_chain(chain_id).assets)


def erc20s_of_chain(chain_id: int) -> list[Erc20Asset]:
    return [
        asset
        for asset in get_chain(chain_id).assets
        if asset.type == AssetType.ERC20
    ]


def nfts_of_chain(chain_id: int) -> list[Erc721Asset]:
    return [
        asset
        for asset in get_chain(chain_id).assets
        if asset.type == AssetType.ERC721
    ]


def asset_by_symbol(chain_id: int, symbol: str) -> Asset | None:
    return load_registry().by_symbol.get((chain_id, symbol.upper()))


def asset_by_address(chain_id: int, address: str) -> Asset | None:
    if _ADDRESS_RE.fullmatch(address) is None:
        return None
    return load_registry().by_address.get((chain_id, address.lower()))


def get_asset(chain_id: int, key: str) -> Asset:
    if _ADDRESS_RE.fullmatch(key) is not None:
        if key.lower() == _NATIVE_SENTINEL_LOOKUP:
            return native_asset(chain_id)
        asset = asset_by_address(chain_id, key)
    else:
        asset = asset_by_symbol(chain_id, key)
    if asset is None:
        msg = f"unknown asset {key} on chain {chain_id}"
        raise KeyError(msg)
    return asset


def native_asset(chain_id: int) -> NativeAsset:
    for asset in get_chain(chain_id).assets:
        if asset.type == AssetType.NATIVE:
            return asset
    msg = f"chain {chain_id} has no native asset"
    raise KeyError(msg)


def decimals_of(asset: Asset) -> int:
    return asset.decimals


def explorer_tx_url(chain_id: int, tx_hash: str) -> str:
    return get_chain(chain_id).explorer_tx_url.replace("{hash}", tx_hash)


def explorer_address_url(chain_id: int, address: str) -> str:
    if _ADDRESS_RE.fullmatch(address) is None:
        msg = f"invalid address: {address}"
        raise ValueError(msg)
    return get_chain(chain_id).explorer_address_url.replace("{address}", to_checksum_address(address))


def derivation_path(chain_id: int, hd_index: int) -> str:
    chain = get_chain(chain_id)
    if hd_index < 0:
        msg = "hd_index must be non-negative"
        raise ValueError(msg)
    return f"m/44'/{chain.coin_type}'/0'/0/{hd_index}"


def format_amount(asset: Asset, base_units: int | str) -> str:
    return _format_amount(asset, base_units)


def parse_amount(asset: Asset, human: str) -> int:
    return _parse_amount(asset, human)


def content_hash() -> str:
    # Canonical format pinned to match the TS `canonicalRows` byte-for-byte so the TS and Python
    # hashes are comparable in CI: per asset, fields [chain_id, type, lower(address|""), UPPER(symbol),
    # decimals] joined by "|"; rows sorted as strings and joined by "\n"; sha256 hex.
    rows: list[str] = []
    for chain in load_registry().chains.values():
        for asset in chain.assets:
            address = getattr(asset, "address", "") or ""
            rows.append(
                "|".join(
                    [
                        str(chain.chain_id),
                        asset.type.value,
                        address.lower(),
                        asset.symbol.upper(),
                        str(asset.decimals),
                    ],
                ),
            )
    encoded = "\n".join(sorted(rows))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
