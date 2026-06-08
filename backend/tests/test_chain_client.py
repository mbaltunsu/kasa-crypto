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
    internal_transfers_from_trace,
    topic_to_address,
)
from app.chain.types import NATIVE_LOG_INDEX, Erc20Transfer

DEPOSIT = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
DEAD = "0x000000000000000000000000000000000000dEaD"


def test_internal_transfers_from_trace_collects_value_calls_to_watched_addresses() -> None:
    """#11: enumerate contract internal calls that move native value to a deposit address, with
    stable, distinct negative log indices (so multiple internal transfers in one tx don't collide
    and never clash with the top-level-native sentinel)."""
    traced = [
        {
            "txHash": "0x" + "11" * 32,
            "result": {
                "type": "CALL",
                "to": "0xC0ffee0000000000000000000000000000000000",  # a contract, not a deposit
                "value": "0x0",
                "calls": [
                    {"type": "CALL", "to": DEAD, "value": "0x1", "calls": []},  # not watched
                    {
                        "type": "CALL",
                        "to": DEPOSIT,
                        "value": "0x64",  # 100 wei → deposit
                        "calls": [
                            {"type": "CALL", "to": DEPOSIT, "value": "0x5", "calls": []},  # nested 5 wei
                        ],
                    },
                    {"type": "CALL", "to": DEPOSIT, "value": "0x0", "calls": []},  # zero value → skip
                ],
            },
        },
    ]
    out = internal_transfers_from_trace(
        traced, wanted_lower={DEPOSIT.lower()}, block_number=100, block_hash="0x" + "aa" * 32,
    )
    assert [t.value for t in out] == [100, 5]
    assert all(t.to_address == DEPOSIT for t in out)  # checksummed
    assert all(t.tx_hash == "0x" + "11" * 32 and t.block_number == 100 for t in out)
    assert len({t.log_index for t in out}) == 2  # distinct
    assert all(t.log_index < NATIVE_LOG_INDEX for t in out)  # below -1, never collides with top-level


def test_internal_transfers_from_trace_skips_reverted_subtrees() -> None:
    traced = [
        {
            "txHash": "0x" + "22" * 32,
            "result": {
                "calls": [
                    {
                        "type": "CALL",
                        "to": DEPOSIT,
                        "value": "0xa",
                        "error": "execution reverted",  # this call (and its children) moved nothing
                        "calls": [{"type": "CALL", "to": DEPOSIT, "value": "0xa", "calls": []}],
                    },
                ],
            },
        },
    ]
    out = internal_transfers_from_trace(
        traced, wanted_lower={DEPOSIT.lower()}, block_number=1, block_hash="0x" + "bb" * 32,
    )
    assert out == []

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


def test_sign_native_is_pure_and_broadcast_raw_resends_the_same_tx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#3: signing is network-free and produces a stable (raw, tx_hash); broadcast_raw sends that
    exact payload. Signing the same inputs twice yields the identical raw so a re-broadcast is the
    same transaction (same hash, same nonce), never a fresh one."""
    eth = _FakeEth(send_behavior="ok", known=False)
    client = _client_with(monkeypatch, eth)

    signed = client.sign_native(private_key=SEND_KEY, to_address=SEND_TO, value=1, nonce=0, gas_price=1)
    assert signed.raw.startswith("0x")
    assert signed.tx_hash.startswith("0x")
    assert len(signed.tx_hash) == 66
    assert len(eth.sent) == 0  # signing did not touch the network

    again = client.sign_native(private_key=SEND_KEY, to_address=SEND_TO, value=1, nonce=0, gas_price=1)
    assert again.raw == signed.raw  # deterministic → re-broadcast is idempotent

    returned = client.broadcast_raw(signed.raw)
    assert returned == "0x" + "42" * 32
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


# ── multi-provider failover for tx/receipt lookups (finding #4) ────────────────
#
# `get_transaction` / `get_transaction_receipt` raise TransactionNotFound (a NORMAL return after the
# client maps it to None/False), which must NOT short-circuit failover: a tx that a lagging provider
# hasn't seen yet may be known to another. "Not found" may only be concluded after ALL providers
# agree, or the lost-broadcast custody guarantee breaks (a real payout gets wrongly reversed).

TX = "0x" + "42" * 32


class _LookupEth:
    def __init__(self, *, knows: bool, reachable: bool = True) -> None:
        self.knows = knows
        self.reachable = reachable

    def get_transaction(self, tx_hash: str) -> dict[str, str]:
        from web3.exceptions import TransactionNotFound

        if not self.reachable:
            raise ValueError("boom: connection reset")
        if self.knows:
            return {"hash": tx_hash}
        raise TransactionNotFound("not found")

    def get_transaction_receipt(self, tx_hash: str) -> dict[str, object]:
        from web3.exceptions import TransactionNotFound

        if not self.reachable:
            raise ValueError("boom: connection reset")
        if self.knows:
            return {
                "transactionHash": tx_hash,
                "status": 1,
                "blockNumber": 5,
                "blockHash": "0x" + "ab" * 32,
            }
        raise TransactionNotFound("not found")


def _multi_client(monkeypatch: pytest.MonkeyPatch, *eths: _LookupEth) -> ChainClient:
    client = ChainClient(11_155_111, ["http://a", "http://b"], max_retries=1)
    monkeypatch.setattr(client, "_providers", lambda: [_FakeWeb3(e) for e in eths])  # type: ignore[arg-type]
    return client


def test_tx_known_true_when_only_a_later_provider_has_it(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _multi_client(monkeypatch, _LookupEth(knows=False), _LookupEth(knows=True))
    assert client._tx_known(TX) is True


def test_tx_known_false_only_after_every_provider_checked(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _multi_client(monkeypatch, _LookupEth(knows=False), _LookupEth(knows=False))
    assert client._tx_known(TX) is False


def test_get_receipt_found_when_only_a_later_provider_has_it(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _multi_client(monkeypatch, _LookupEth(knows=False), _LookupEth(knows=True))
    receipt = client.get_receipt(TX)
    assert receipt is not None
    assert receipt.status == 1
    assert receipt.block_number == 5


# ── block_hash: not-found vs RPC outage (finding #18) ──────────────────────────


class _BlockEth:
    def __init__(self, *, has_block: bool, reachable: bool = True, block_hash: str = "0x" + "ab" * 32) -> None:
        self.has_block = has_block
        self.reachable = reachable
        self.block_hash = block_hash

    def get_block(self, block_number: int, *, full_transactions: bool = False) -> dict[str, str]:
        from web3.exceptions import BlockNotFound

        if not self.reachable:
            raise ValueError("boom: connection reset")
        if self.has_block:
            return {"hash": self.block_hash}
        raise BlockNotFound("no block")


def test_block_hash_none_when_all_providers_report_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _multi_client(monkeypatch, _BlockEth(has_block=False), _BlockEth(has_block=False))  # type: ignore[arg-type]
    assert client.block_hash(100) is None  # genuinely not-yet-mined → retry, not an error


def test_block_hash_raises_on_total_rpc_outage(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _multi_client(monkeypatch, _BlockEth(has_block=False, reachable=False))  # type: ignore[arg-type]
    with pytest.raises(ChainRpcError):  # an outage must NOT masquerade as "block not found"
        client.block_hash(100)


def test_block_hash_found_on_a_later_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _multi_client(
        monkeypatch,
        _BlockEth(has_block=False),  # type: ignore[arg-type]
        _BlockEth(has_block=True, block_hash="0x" + "cd" * 32),  # type: ignore[arg-type]
    )
    assert client.block_hash(100) == "0x" + "cd" * 32
