from __future__ import annotations

import re

_HEX_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
_ZERO_ADDRESS = "0x" + "0" * 40


class InvalidAddressError(ValueError):
    """A user-supplied EVM address failed validation."""


def to_checksum_address_strict(address: str) -> str:
    """Validate an EVM address and return its EIP-55 checksummed form.

    Rejects anything that is not a 0x-prefixed 20-byte hex string, rejects the zero/burn address,
    and rejects mixed-case input whose EIP-55 checksum does not match — so a single mistyped hex
    digit is caught instead of being silently re-checksummed and sent to the wrong (valid) address
    (finding #14). All-lowercase / all-uppercase input carries no checksum and is normalized.
    """
    if not _HEX_ADDRESS.match(address):
        msg = "address must be a 0x-prefixed 40-hex-character EVM address"
        raise InvalidAddressError(msg)
    if address.lower() == _ZERO_ADDRESS:
        msg = "the zero address is not a valid destination"
        raise InvalidAddressError(msg)

    from eth_utils import to_checksum_address

    checksummed = str(to_checksum_address(address))
    body = address[2:]
    is_mixed_case = body != body.lower() and body != body.upper()
    if is_mixed_case and address != checksummed:
        msg = "address EIP-55 checksum is invalid"
        raise InvalidAddressError(msg)
    return checksummed
