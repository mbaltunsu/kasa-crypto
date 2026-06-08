import pytest

pytest.importorskip("bip_utils")
pytest.importorskip("eth_utils")

from app.core.hd_wallet import (
    derive_account,
    derive_deposit_address,
    derive_hot_wallet,
    hot_wallet_account,
)

# Well-known BIP-39 test vector (MetaMask default test mnemonic).
KNOWN_MNEMONIC = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
KNOWN_ADDRESS_0 = "0x9858EfFD232B4033E47d90003D41EC34EcaEda94"
KNOWN_PRIVKEY_0 = "0x1ab42cc412b618bdea3a599e3c9bae199ebf030895b039e9db1e30dafb12b727"


def test_bip39_known_vector_eth_account_zero() -> None:
    derived = derive_hot_wallet(KNOWN_MNEMONIC, chain_id=11_155_111)

    assert derived.derivation_path == "m/44'/60'/0'/0/0"
    assert derived.address == KNOWN_ADDRESS_0


def test_deposit_index_zero_is_reserved() -> None:
    with pytest.raises(ValueError):
        derive_deposit_address(KNOWN_MNEMONIC, chain_id=11_155_111, hd_index=0)


def test_derive_account_exposes_signing_private_key() -> None:
    account = derive_account(KNOWN_MNEMONIC, chain_id=11_155_111, hd_index=0)

    assert account.address == KNOWN_ADDRESS_0
    assert account.private_key == KNOWN_PRIVKEY_0
    assert account.derivation_path == "m/44'/60'/0'/0/0"


def test_hot_wallet_account_is_index_zero() -> None:
    account = hot_wallet_account(KNOWN_MNEMONIC)

    assert account.address == KNOWN_ADDRESS_0
    assert account.private_key == KNOWN_PRIVKEY_0


def test_private_key_is_stable_across_evm_chains() -> None:
    # Coin type 60 → identical key material on every EVM chain; only the path label differs.
    sepolia = derive_account(KNOWN_MNEMONIC, chain_id=11_155_111, hd_index=1)
    fuji = derive_account(KNOWN_MNEMONIC, chain_id=43_113, hd_index=1)

    assert sepolia.private_key == fuji.private_key
    assert sepolia.address == fuji.address
