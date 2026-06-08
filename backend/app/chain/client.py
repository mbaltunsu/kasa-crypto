"""Concrete web3-backed chain client + its network-free encoding helpers.

This is the *only* module that talks to an EVM RPC. Everything web3-specific is confined here
and imported lazily (matching the rest of the backend) so test collection and the API process
never pay for web3 unless they actually reach a chain. Workers depend on the protocols in
`types.py`; this class structurally satisfies all of them.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

from app.chain.types import Erc20Transfer, NativeTransfer, TxReceipt

if TYPE_CHECKING:
    from app.core.config import Settings

T = TypeVar("T")

# keccak256("Transfer(address,address,uint256)") — identical for ERC-20 and ERC-721.
ERC20_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# Gas limits: a bare value transfer is always 21000; an ERC-20 transfer gets generous head-room.
NATIVE_TRANSFER_GAS = 21_000
ERC20_TRANSFER_GAS = 90_000

ERC20_MIN_ABI: list[dict[str, object]] = [
    {
        "constant": True,
        "inputs": [{"name": "owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


class ChainRpcError(RuntimeError):
    """Raised when every configured RPC provider failed a call after retries."""


# Error fragments that mean "a tx with this nonce/hash is ALREADY on the chain or in the mempool"
# — i.e. the broadcast effectively succeeded and must NOT be treated as a failed send.
_ALREADY_BROADCAST_MARKERS = (
    "already known",
    "known transaction",
    "alreadyknown",
    "nonce too low",
    "already imported",
    "replacement transaction underpriced",
)


def _is_already_broadcast(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _ALREADY_BROADCAST_MARKERS)


# ─────────────────────────── pure helpers (no network) ───────────────────────────


def block_ranges(from_block: int, to_block: int, chunk_size: int) -> list[tuple[int, int]]:
    """Split an inclusive [from_block, to_block] span into ≤ chunk_size sub-ranges."""
    if chunk_size <= 0:
        msg = "chunk_size must be positive"
        raise ValueError(msg)
    if from_block > to_block:
        return []
    ranges: list[tuple[int, int]] = []
    start = from_block
    while start <= to_block:
        end = min(start + chunk_size - 1, to_block)
        ranges.append((start, end))
        start = end + 1
    return ranges


def address_to_topic(address: str) -> str:
    """Left-pad a 20-byte address into a 32-byte (lowercase) log topic."""
    return "0x" + "0" * 24 + address[2:].lower()


def topic_to_address(topic: str) -> str:
    from eth_utils import to_checksum_address

    return str(to_checksum_address("0x" + topic[-40:]))


def _checksum(address: str) -> str:
    from eth_utils import to_checksum_address

    return str(to_checksum_address(address))


def _to_hex(value: object) -> str:
    if isinstance(value, str):
        return value if value.startswith("0x") else "0x" + value
    if isinstance(value, (bytes, bytearray)):
        return "0x" + bytes(value).hex()
    msg = f"cannot hex-encode {type(value)!r}"
    raise TypeError(msg)


def decode_erc20_transfer(
    *,
    token_address: str,
    topics: list[str],
    data: str,
    tx_hash: str,
    log_index: int,
    block_number: int,
    block_hash: str,
) -> Erc20Transfer:
    raw = data.removeprefix("0x")
    value = int(raw, 16) if raw else 0
    return Erc20Transfer(
        token_address=_checksum(token_address),
        from_address=topic_to_address(topics[1]),
        to_address=topic_to_address(topics[2]),
        value=value,
        tx_hash=tx_hash,
        log_index=log_index,
        block_number=block_number,
        block_hash=block_hash,
    )


# ─────────────────────────── web3-backed client ───────────────────────────


class ChainClient:
    chain_id: int

    def __init__(
        self,
        chain_id: int,
        rpc_urls: list[str],
        *,
        max_retries: int = 3,
        request_timeout: float = 20.0,
        block_chunk_size: int = 2_000,
    ) -> None:
        if not rpc_urls:
            msg = f"chain {chain_id} has no RPC URLs configured"
            raise ValueError(msg)
        self.chain_id = chain_id
        self._rpc_urls = list(rpc_urls)
        self._max_retries = max(1, max_retries)
        self._request_timeout = request_timeout
        self._block_chunk_size = max(1, block_chunk_size)
        self._web3s: list[Any] | None = None

    @classmethod
    def from_settings(cls, chain_id: int, settings: Settings) -> ChainClient:
        return cls(
            chain_id,
            settings.rpc_urls(chain_id),
            max_retries=settings.rpc_max_retries,
            request_timeout=settings.rpc_request_timeout,
            block_chunk_size=settings.block_chunk_size,
        )

    def _providers(self) -> list[Any]:
        if self._web3s is None:
            from web3 import HTTPProvider, Web3

            self._web3s = [
                Web3(HTTPProvider(url, request_kwargs={"timeout": self._request_timeout}))
                for url in self._rpc_urls
            ]
        return self._web3s

    def _with_failover(self, label: str, fn: Callable[[Any], T]) -> T:
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            for web3 in self._providers():
                try:
                    return fn(web3)
                except Exception as exc:  # noqa: BLE001 - resilience: fall through to next provider
                    last_exc = exc
            if attempt + 1 < self._max_retries:
                time.sleep(min(0.5 * 2**attempt, 5.0))
        msg = f"all RPC providers failed for {label} on chain {self.chain_id}: {last_exc}"
        raise ChainRpcError(msg) from last_exc

    def _get_logs(self, log_filter: dict[str, Any]) -> list[Any]:
        return self._with_failover("get_logs", lambda w3: w3.eth.get_logs(log_filter))

    def _get_block(self, block_number: int, *, full_transactions: bool = False) -> Any:
        return self._with_failover(
            "get_block",
            lambda w3: w3.eth.get_block(block_number, full_transactions=full_transactions),
        )

    # ── reads (WatcherClient / BalanceClient) ──────────────────────────────────

    def block_number(self) -> int:
        return int(self._with_failover("block_number", lambda w3: w3.eth.block_number))

    def block_hash(self, block_number: int) -> str | None:
        try:
            block = self._get_block(block_number)
        except ChainRpcError:
            return None
        return _to_hex(block["hash"])

    def fetch_erc20_transfers(
        self,
        *,
        token_addresses: list[str],
        to_addresses: list[str],
        from_block: int,
        to_block: int,
    ) -> list[Erc20Transfer]:
        if not token_addresses or not to_addresses or from_block > to_block:
            return []
        addresses = [_checksum(address) for address in token_addresses]
        to_topics = [address_to_topic(address) for address in to_addresses]
        transfers: list[Erc20Transfer] = []
        for low, high in block_ranges(from_block, to_block, self._block_chunk_size):
            log_filter: dict[str, Any] = {
                "address": addresses,
                "fromBlock": low,
                "toBlock": high,
                "topics": [ERC20_TRANSFER_TOPIC, None, to_topics],
            }
            transfers.extend(
                decode_erc20_transfer(
                    token_address=_to_hex(log["address"]),
                    topics=[_to_hex(topic) for topic in log["topics"]],
                    data=_to_hex(log["data"]),
                    tx_hash=_to_hex(log["transactionHash"]),
                    log_index=int(log["logIndex"]),
                    block_number=int(log["blockNumber"]),
                    block_hash=_to_hex(log["blockHash"]),
                )
                for log in self._get_logs(log_filter)
            )
        return transfers

    def fetch_native_transfers(
        self,
        *,
        to_addresses: list[str],
        from_block: int,
        to_block: int,
    ) -> list[NativeTransfer]:
        if not to_addresses or from_block > to_block:
            return []
        wanted = {address.lower() for address in to_addresses}
        transfers: list[NativeTransfer] = []
        for block_no in range(from_block, to_block + 1):
            block = self._get_block(block_no, full_transactions=True)
            block_hash = _to_hex(block["hash"])
            for tx in block["transactions"]:
                to_address = tx["to"]
                value = int(tx["value"])
                if to_address is not None and value > 0 and to_address.lower() in wanted:
                    transfers.append(
                        NativeTransfer(
                            to_address=_checksum(to_address),
                            value=value,
                            tx_hash=_to_hex(tx["hash"]),
                            block_number=block_no,
                            block_hash=block_hash,
                        ),
                    )
        return transfers

    def native_balance(self, address: str) -> int:
        return int(
            self._with_failover("get_balance", lambda w3: w3.eth.get_balance(_checksum(address))),
        )

    def erc20_balance(self, *, token_address: str, address: str) -> int:
        def call(web3: Any) -> int:
            contract = web3.eth.contract(address=_checksum(token_address), abi=ERC20_MIN_ABI)
            return int(contract.functions.balanceOf(_checksum(address)).call())

        return self._with_failover("balanceOf", call)

    # ── writes (SenderClient) ──────────────────────────────────────────────────

    def pending_nonce(self, address: str) -> int:
        return int(
            self._with_failover(
                "nonce",
                lambda w3: w3.eth.get_transaction_count(_checksum(address), "pending"),
            ),
        )

    def latest_nonce(self, address: str) -> int:
        return int(
            self._with_failover(
                "latest_nonce",
                lambda w3: w3.eth.get_transaction_count(_checksum(address), "latest"),
            ),
        )

    def suggested_gas_price(self) -> int:
        return int(self._with_failover("gas_price", lambda w3: w3.eth.gas_price))

    def _tx_known(self, tx_hash: str) -> bool:
        """True if any provider already has this tx (pending or mined)."""

        def fetch(web3: Any) -> bool:
            from web3.exceptions import TransactionNotFound

            try:
                web3.eth.get_transaction(tx_hash)
            except TransactionNotFound:
                return False
            return True

        try:
            return self._with_failover("get_transaction", fetch)
        except ChainRpcError:
            return False

    def _broadcast(self, signed: Any) -> str:
        """Broadcast a pre-signed tx, returning its hash.

        Critically, a send is reported as successful whenever the tx is (or becomes) known to a node
        — including when send_raw_transaction raises 'already known' / 'nonce too low' after the tx
        was accepted, or the HTTP response was lost. We only raise ChainRpcError once the tx is
        verified absent from every provider, so a withdrawal is never falsely reversed while its
        payout actually confirms on-chain.
        """
        expected = _to_hex(signed.hash)
        raw = signed.raw_transaction
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            for web3 in self._providers():
                try:
                    return _to_hex(web3.eth.send_raw_transaction(raw))
                except Exception as exc:  # noqa: BLE001 - classify: the tx may already be broadcast
                    last_exc = exc
                    if _is_already_broadcast(exc) and self._tx_known(expected):
                        return expected
            if attempt + 1 < self._max_retries:
                time.sleep(min(0.5 * 2**attempt, 5.0))
        if self._tx_known(expected):
            return expected
        msg = f"failed to broadcast tx {expected} on chain {self.chain_id}: {last_exc}"
        raise ChainRpcError(msg) from last_exc

    def send_native(
        self,
        *,
        private_key: str,
        to_address: str,
        value: int,
        nonce: int,
        gas_price: int,
    ) -> str:
        from eth_account import Account

        account = Account.from_key(private_key)
        tx = {
            "to": _checksum(to_address),
            "value": value,
            "nonce": nonce,
            "gas": NATIVE_TRANSFER_GAS,
            "gasPrice": gas_price,
            "chainId": self.chain_id,
        }
        return self._broadcast(account.sign_transaction(tx))

    def send_erc20(
        self,
        *,
        private_key: str,
        token_address: str,
        to_address: str,
        value: int,
        nonce: int,
        gas_price: int,
    ) -> str:
        from eth_account import Account

        account = Account.from_key(private_key)
        # Build + sign once (all tx fields are supplied, so this is pure encoding, no RPC), then
        # broadcast the fixed signed payload so retries/failover re-send the identical tx.
        web3 = self._providers()[0]
        contract = web3.eth.contract(address=_checksum(token_address), abi=ERC20_MIN_ABI)
        tx = contract.functions.transfer(_checksum(to_address), value).build_transaction(
            {
                "from": account.address,
                "nonce": nonce,
                "gas": ERC20_TRANSFER_GAS,
                "gasPrice": gas_price,
                "chainId": self.chain_id,
            },
        )
        return self._broadcast(account.sign_transaction(tx))

    def get_receipt(self, tx_hash: str) -> TxReceipt | None:
        def fetch(web3: Any) -> Any:
            from web3.exceptions import TransactionNotFound

            try:
                return web3.eth.get_transaction_receipt(tx_hash)
            except TransactionNotFound:
                return None

        receipt = self._with_failover("receipt", fetch)
        if receipt is None:
            return None
        return TxReceipt(
            tx_hash=_to_hex(receipt["transactionHash"]),
            status=int(receipt["status"]),
            block_number=int(receipt["blockNumber"]),
            block_hash=_to_hex(receipt["blockHash"]),
        )
