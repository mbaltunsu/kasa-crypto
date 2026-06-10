from kasa_shared.consts import NATIVE_ASSET_SENTINEL, AssetType
from kasa_shared.registry import (
    asset_by_address,
    asset_by_symbol,
    content_hash,
    decimals_of,
    derivation_path,
    erc20s_of_chain,
    explorer_address_url,
    explorer_tx_url,
    get_asset,
    get_chain,
    list_chains,
    native_asset,
    nfts_of_chain,
    tokens_of_chain,
)

from app.services.registry_projection import asset_responses

SEPOLIA = 11_155_111
TOKEN_COUNT_PER_CHAIN = 3
EVM_ADDRESS_LENGTH = 42
DEMO_DECIMALS = 18


def test_registry_lookups() -> None:
    sepolia = get_chain(SEPOLIA)
    assert sepolia.name == "ethereum-sepolia"
    assert {chain.chain_id for chain in list_chains()} == {SEPOLIA, 43_113, 31_337}
    assert len(tokens_of_chain(SEPOLIA)) == TOKEN_COUNT_PER_CHAIN
    assert erc20s_of_chain(SEPOLIA)[0].symbol == "DEMO"
    assert nfts_of_chain(SEPOLIA)[0].symbol == "KASA"
    assert asset_by_symbol(SEPOLIA, "demo") is not None
    assert get_asset(SEPOLIA, "ETH").type == AssetType.NATIVE
    assert get_asset(SEPOLIA, NATIVE_ASSET_SENTINEL).type == AssetType.NATIVE


def test_native_has_no_address_and_symbols_never_0x_prefixed() -> None:
    for chain in list_chains():
        native = native_asset(chain.chain_id)
        assert not hasattr(native, "address")
        for asset in chain.assets:
            assert not asset.symbol.lower().startswith("0x")


def test_address_indices_and_urls() -> None:
    demo = erc20s_of_chain(SEPOLIA)[0]
    # DEMO is deployed → a real EIP-55 address that round-trips through the address index; the
    # zero address is never indexed.
    assert demo.address.startswith("0x")
    assert len(demo.address) == EVM_ADDRESS_LENGTH
    indexed = asset_by_address(SEPOLIA, demo.address)
    assert indexed is not None
    assert indexed.symbol == "DEMO"
    assert asset_by_address(SEPOLIA, "0x0000000000000000000000000000000000000000") is None
    assert explorer_tx_url(SEPOLIA, "0xabc").endswith("/tx/0xabc")
    assert explorer_address_url(SEPOLIA, "0x0000000000000000000000000000000000000000").endswith(
        "/address/0x0000000000000000000000000000000000000000",
    )
    assert derivation_path(SEPOLIA, 7) == "m/44'/60'/0'/0/7"
    assert decimals_of(demo) == DEMO_DECIMALS


def test_content_hash_stable() -> None:
    # MUST equal the TS `canonicalRows` sha256 (packages/shared check:parity) — this is the
    # cross-language registry parity gate. Do not change without changing the TS side identically.
    assert content_hash() == "a55deaff545faff9dc360fb642230d3e1bab844237ff730a8c3e67974d2826b4"


def test_asset_responses_include_serialized_max_amount() -> None:
    assets = asset_responses(SEPOLIA)
    by_symbol = {asset.symbol: asset for asset in assets}

    assert by_symbol["ETH"].model_dump(mode="json")["max_amount"] == "1000000000000000"
    assert by_symbol["DEMO"].model_dump(mode="json")["max_amount"] == "100000000000000000000"
    assert by_symbol["KASA"].model_dump(mode="json")["max_amount"] is None
