"""Network-free data structures and the chain-client protocols the workers depend on.

The watcher and withdrawer are written against these protocols, never against web3 directly,
so they can be unit-tested with an injected fake. The concrete `ChainClient` (client.py) is the
only place web3/RPC lives and it structurally satisfies all three protocols.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

# Native value transfers carry no log index; this sentinel makes (chain_id, tx_hash, log_index) a
# stable, non-NULL dedup key for them. Real ERC-20 log indices are always >= 0.
NATIVE_LOG_INDEX = -1


@dataclass(frozen=True)
class Erc20Transfer:
    token_address: str  # EIP-55 checksummed contract address
    from_address: str
    to_address: str
    value: int
    tx_hash: str
    log_index: int
    block_number: int
    block_hash: str


@dataclass(frozen=True)
class NativeTransfer:
    to_address: str
    value: int
    tx_hash: str
    block_number: int
    block_hash: str


@dataclass(frozen=True)
class TxReceipt:
    tx_hash: str
    status: int  # 1 = success, 0 = reverted
    block_number: int
    block_hash: str


class WatcherClient(Protocol):
    """Read side: everything the deposit watcher needs to index a chain."""

    chain_id: int

    def block_number(self) -> int: ...

    def block_hash(self, block_number: int) -> str | None: ...

    def fetch_erc20_transfers(
        self,
        *,
        token_addresses: list[str],
        to_addresses: list[str],
        from_block: int,
        to_block: int,
    ) -> list[Erc20Transfer]: ...

    def fetch_native_transfers(
        self,
        *,
        to_addresses: list[str],
        from_block: int,
        to_block: int,
    ) -> list[NativeTransfer]: ...


class SenderClient(Protocol):
    """Write side: nonce, fees, signing+broadcast, and receipt polling."""

    chain_id: int

    def pending_nonce(self, address: str) -> int: ...

    def latest_nonce(self, address: str) -> int: ...

    def suggested_gas_price(self) -> int: ...

    def send_native(
        self,
        *,
        private_key: str,
        to_address: str,
        value: int,
        nonce: int,
        gas_price: int,
    ) -> str: ...

    def send_erc20(
        self,
        *,
        private_key: str,
        token_address: str,
        to_address: str,
        value: int,
        nonce: int,
        gas_price: int,
    ) -> str: ...

    def get_receipt(self, tx_hash: str) -> TxReceipt | None: ...


class BalanceClient(Protocol):
    """Balance reads for proof-of-reserves."""

    chain_id: int

    def native_balance(self, address: str) -> int: ...

    def erc20_balance(self, *, token_address: str, address: str) -> int: ...
