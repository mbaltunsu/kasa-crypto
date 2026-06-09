from kasa_shared.consts import AssetType, NATIVE_ASSET_SENTINEL
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


def test_registry_lookups() -> None:
    sepolia = get_chain(11_155_111)
    assert sepolia.name == "ethereum-sepolia"
    assert {chain.chain_id for chain in list_chains()} == {11_155_111, 43_113, 31_337}
    assert len(tokens_of_chain(11_155_111)) == 3
    assert erc20s_of_chain(11_155_111)[0].symbol == "DEMO"
    assert nfts_of_chain(11_155_111)[0].symbol == "KASA"
    assert asset_by_symbol(11_155_111, "demo") is not None
    assert get_asset(11_155_111, "ETH").type == AssetType.NATIVE
    assert get_asset(11_155_111, NATIVE_ASSET_SENTINEL).type == AssetType.NATIVE


def test_native_has_no_address_and_symbols_never_0x_prefixed() -> None:
    for chain in list_chains():
        native = native_asset(chain.chain_id)
        assert not hasattr(native, "address")
        for asset in chain.assets:
            assert not asset.symbol.lower().startswith("0x")


def test_address_indices_and_urls() -> None:
    demo = erc20s_of_chain(11_155_111)[0]
    # DEMO is deployed → a real EIP-55 address that round-trips through the address index; the
    # zero address is never indexed.
    assert demo.address.startswith("0x")
    assert len(demo.address) == 42
    indexed = asset_by_address(11_155_111, demo.address)
    assert indexed is not None
    assert indexed.symbol == "DEMO"
    assert asset_by_address(11_155_111, "0x0000000000000000000000000000000000000000") is None
    assert explorer_tx_url(11_155_111, "0xabc").endswith("/tx/0xabc")
    assert explorer_address_url(11_155_111, "0x0000000000000000000000000000000000000000").endswith(
        "/address/0x0000000000000000000000000000000000000000",
    )
    assert derivation_path(11_155_111, 7) == "m/44'/60'/0'/0/7"
    assert decimals_of(demo) == 18


def test_content_hash_stable() -> None:
    # MUST equal the TS `canonicalRows` sha256 (packages/shared check:parity) — this is the
    # cross-language registry parity gate. Do not change without changing the TS side identically.
    assert content_hash() == "a55deaff545faff9dc360fb642230d3e1bab844237ff730a8c3e67974d2826b4"
