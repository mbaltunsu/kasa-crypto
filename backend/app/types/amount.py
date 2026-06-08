import re
from decimal import Decimal
from typing import Annotated, Protocol

from pydantic import AfterValidator, BeforeValidator, PlainSerializer, WithJsonSchema

_PAT = r"^-?(0|[1-9]\d*)$"
_WIRE_RE = re.compile(_PAT)


class SupportsAmountMetadata(Protocol):
    symbol: str
    decimals: int


def _to_int(value: object) -> int:
    if isinstance(value, bool):
        msg = "base-unit amount must not be a boolean"
        raise ValueError(msg)
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        # Postgres Numeric(78,0) deserializes to Decimal; accept it iff it is a whole number.
        if value != value.to_integral_value():
            msg = "base-unit amount must be a whole number"
            raise ValueError(msg)
        return int(value)
    if isinstance(value, str):
        if _WIRE_RE.fullmatch(value) is None:
            msg = "base-unit amount must be an integer string without leading zeros"
            raise ValueError(msg)
        return int(value)
    msg = "base-unit amount must be an integer string or int"
    raise ValueError(msg)


def _nonneg(value: int) -> int:
    if value < 0:
        msg = "base-unit amount must be non-negative"
        raise ValueError(msg)
    return value


BaseUnit = Annotated[
    int,
    BeforeValidator(_to_int),
    PlainSerializer(lambda value: str(value), return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "pattern": _PAT}, mode="validation"),
    WithJsonSchema({"type": "string", "pattern": _PAT}, mode="serialization"),
]

UnsignedBaseUnit = Annotated[BaseUnit, AfterValidator(_nonneg)]


def parse_amount(asset: SupportsAmountMetadata, human: str) -> int:
    decimals = asset.decimals
    raw = human.strip()
    if raw == "":
        msg = "amount is required"
        raise ValueError(msg)

    neg = raw.startswith("-")
    unsigned = raw[1:] if neg else raw
    if unsigned == "" or unsigned == "." or unsigned.count(".") > 1:
        msg = f"invalid amount for {asset.symbol}"
        raise ValueError(msg)

    whole, _, frac = unsigned.partition(".")
    if (whole and not whole.isdigit()) or (frac and not frac.isdigit()):
        msg = f"invalid amount for {asset.symbol}"
        raise ValueError(msg)
    if whole == "" and frac == "":
        msg = f"invalid amount for {asset.symbol}"
        raise ValueError(msg)
    if len(frac) > decimals:
        msg = f"too many decimals for {asset.symbol} (max {decimals})"
        raise ValueError(msg)

    digits = (whole or "0") + frac.ljust(decimals, "0")
    value = int(digits)
    return -value if neg else value


def format_amount(asset: SupportsAmountMetadata, base_units: int | str) -> str:
    value = _to_int(base_units)
    decimals = asset.decimals
    neg = value < 0
    digits = str(abs(value))

    if decimals == 0:
        formatted = digits
    else:
        padded = digits.zfill(decimals + 1)
        whole = padded[:-decimals]
        frac = padded[-decimals:].rstrip("0")
        formatted = whole if frac == "" else f"{whole}.{frac}"

    return f"-{formatted}" if neg and formatted != "0" else formatted
