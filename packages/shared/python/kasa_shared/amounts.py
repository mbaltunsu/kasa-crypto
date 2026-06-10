from typing import Protocol


class SupportsAmountMetadata(Protocol):
    @property
    def symbol(self) -> str: ...

    @property
    def decimals(self) -> int: ...


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
    value = _base_units_to_int(base_units)
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


def _base_units_to_int(value: int | str) -> int:
    if isinstance(value, bool):
        msg = "base-unit amount must not be a boolean"
        raise ValueError(msg)
    if isinstance(value, int):
        return value
    if value == "":
        msg = "base-unit amount is required"
        raise ValueError(msg)
    if value.startswith("-"):
        digits = value[1:]
    else:
        digits = value
    if digits == "" or not digits.isdigit():
        msg = "base-unit amount must be an integer"
        raise ValueError(msg)
    return int(value)
