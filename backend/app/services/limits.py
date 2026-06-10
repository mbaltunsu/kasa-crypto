from __future__ import annotations

import json
import os
from decimal import Decimal, InvalidOperation
from typing import Protocol

from kasa_shared.consts import AssetType


class SupportsAmountLimit(Protocol):
    @property
    def chain_id(self) -> int: ...

    @property
    def symbol(self) -> str: ...

    @property
    def type(self) -> str: ...

    @property
    def decimals(self) -> int: ...


# (chain_id, symbol) -> max whole units allowed per request.
_DEFAULT_MAX_AMOUNT_WHOLE: dict[tuple[int, str], Decimal] = {
    (11_155_111, "ETH"): Decimal("0.001"),
    (11_155_111, "DEMO"): Decimal(100),
    (43_113, "AVAX"): Decimal("0.05"),
    (43_113, "DEMO"): Decimal(100),
    (31_337, "ETH"): Decimal(1),
    (31_337, "DEMO"): Decimal(100),
}
DEFAULT_MAX_WHOLE = {AssetType.NATIVE: Decimal("0.001"), AssetType.ERC20: Decimal(100)}


def _load_max_amount_whole() -> dict[tuple[int, str], Decimal]:
    caps = dict(_DEFAULT_MAX_AMOUNT_WHOLE)
    raw = os.environ.get("KASA_MAX_AMOUNTS")
    if raw is None:
        return caps

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return caps
    if not isinstance(parsed, dict):
        return caps

    for key, value in parsed.items():
        if not isinstance(key, str):
            continue
        raw_chain_id, separator, symbol = key.partition(":")
        if separator == "" or symbol == "":
            continue
        try:
            chain_id = int(raw_chain_id)
            whole = Decimal(str(value))
        except (InvalidOperation, ValueError):
            continue
        if not whole.is_finite() or whole < 0:
            continue
        caps[(chain_id, symbol.upper())] = whole
    return caps


MAX_AMOUNT_WHOLE: dict[tuple[int, str], Decimal] = _load_max_amount_whole()


def max_amount_base_units(asset: SupportsAmountLimit) -> int | None:
    try:
        asset_type = AssetType(asset.type)
    except ValueError:
        return None

    whole = MAX_AMOUNT_WHOLE.get((asset.chain_id, asset.symbol.upper()))
    if whole is None:
        whole = DEFAULT_MAX_WHOLE.get(asset_type)
    if whole is None:
        return None

    return int(whole * (Decimal(10) ** asset.decimals))
