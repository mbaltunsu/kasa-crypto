"""Unit tests for the pure (network-free) helpers of the chain client.

The web3-backed I/O methods are exercised indirectly through the worker tests, which
inject a fake client. Here we pin the protocol-independent encoding/decoding logic.
"""

import pytest

from app.chain.client import (
    ERC20_TRANSFER_TOPIC,
    address_to_topic,
    block_ranges,
    decode_erc20_transfer,
    topic_to_address,
)
from app.chain.types import Erc20Transfer

# Canonical keccak256("Transfer(address,address,uint256)") — shared by ERC-20 and ERC-721.
EXPECTED_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
ALICE = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"


def test_transfer_topic_matches_keccak() -> None:
    eth_utils = pytest.importorskip("eth_utils")
    computed = "0x" + eth_utils.keccak(text="Transfer(address,address,uint256)").hex()
    assert ERC20_TRANSFER_TOPIC == EXPECTED_TRANSFER_TOPIC
    assert computed == ERC20_TRANSFER_TOPIC


def test_block_ranges_splits_inclusive_range_into_chunks() -> None:
    assert block_ranges(0, 10, 4) == [(0, 3), (4, 7), (8, 10)]
    assert block_ranges(5, 5, 100) == [(5, 5)]
    assert block_ranges(0, 99, 50) == [(0, 49), (50, 99)]


def test_block_ranges_empty_when_from_exceeds_to() -> None:
    assert block_ranges(10, 9, 4) == []


def test_block_ranges_rejects_nonpositive_chunk() -> None:
    with pytest.raises(ValueError):
        block_ranges(0, 10, 0)


def test_address_topic_round_trips() -> None:
    topic = address_to_topic(ALICE)
    assert topic == "0x" + "0" * 24 + ALICE[2:].lower()
    assert topic_to_address(topic) == ALICE  # checksummed back


def test_decode_erc20_transfer_extracts_value_and_parties() -> None:
    sender = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
    transfer = decode_erc20_transfer(
        token_address="0xabc0000000000000000000000000000000000001",
        topics=[
            ERC20_TRANSFER_TOPIC,
            address_to_topic(sender),
            address_to_topic(ALICE),
        ],
        data="0x" + format(1_000_000_000_000_000_000, "064x"),
        tx_hash="0x" + "ab" * 32,
        log_index=7,
        block_number=42,
        block_hash="0x" + "cd" * 32,
    )

    assert transfer == Erc20Transfer(
        token_address="0xABC0000000000000000000000000000000000001",
        from_address=sender,
        to_address=ALICE,
        value=1_000_000_000_000_000_000,
        tx_hash="0x" + "ab" * 32,
        log_index=7,
        block_number=42,
        block_hash="0x" + "cd" * 32,
    )


# ── send/broadcast safety (white-box: inject fake providers) ───────────────────

pytest.importorskip("eth_account")
pytest.importorskip("web3")

from app.chain.client import ChainClient, ChainRpcError  # noqa: E402

SEND_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
SEND_TO = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"


class _FakeEth:
    def __init__(self, *, send_behavior: str, known: bool) -> None:
        self.send_behavior = send_behavior  # "ok" | "already_known" | "boom"
        self.known = known
        self.sent: list[object] = []

    def send_raw_transaction(self, raw: object) -> bytes:
        if self.send_behavior == "ok":
            self.sent.append(raw)
            return b"\x42" * 32
        if self.send_behavior == "already_known":
            raise ValueError("already known")
        raise ValueError("boom: connection reset")

    def get_transaction(self, tx_hash: str) -> dict[str, str]:
        from web3.exceptions import TransactionNotFound

        if self.known:
            return {"hash": tx_hash}
        raise TransactionNotFound("not found")


class _FakeWeb3:
    def __init__(self, eth: _FakeEth) -> None:
        self.eth = eth


def _client_with(monkeypatch: pytest.MonkeyPatch, eth: _FakeEth) -> ChainClient:
    client = ChainClient(11_155_111, ["http://stub"], max_retries=1)
    monkeypatch.setattr(client, "_providers", lambda: [_FakeWeb3(eth)])
    return client


def test_send_returns_node_hash_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    eth = _FakeEth(send_behavior="ok", known=False)
    client = _client_with(monkeypatch, eth)
    tx_hash = client.send_native(private_key=SEND_KEY, to_address=SEND_TO, value=1, nonce=0, gas_price=1)
    assert tx_hash == "0x" + "42" * 32
    assert len(eth.sent) == 1


def test_send_returns_hash_when_tx_already_broadcast(monkeypatch: pytest.MonkeyPatch) -> None:
    # A lost-response / already-known situation must NOT raise: the tx is on-chain, so the caller
    # must learn the hash (and never reverse the reservation).
    eth = _FakeEth(send_behavior="already_known", known=True)
    client = _client_with(monkeypatch, eth)
    tx_hash = client.send_native(private_key=SEND_KEY, to_address=SEND_TO, value=1, nonce=0, gas_price=1)
    assert tx_hash.startswith("0x")
    assert len(tx_hash) == 66


def test_send_raises_only_when_tx_verified_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    eth = _FakeEth(send_behavior="boom", known=False)
    client = _client_with(monkeypatch, eth)
    with pytest.raises(ChainRpcError):
        client.send_native(private_key=SEND_KEY, to_address=SEND_TO, value=1, nonce=0, gas_price=1)
