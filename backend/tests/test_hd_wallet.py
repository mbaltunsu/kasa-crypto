import pytest

pytest.importorskip("bip_utils")
pytest.importorskip("eth_utils")

from app.core.hd_wallet import derive_deposit_address, derive_hot_wallet


def test_bip39_known_vector_eth_account_zero() -> None:
    mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"

    derived = derive_hot_wallet(mnemonic, chain_id=11_155_111)

    assert derived.derivation_path == "m/44'/60'/0'/0/0"
    assert derived.address == "0x9858EfFD232B4033E47d90003D41EC34EcaEda94"


def test_deposit_index_zero_is_reserved() -> None:
    mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"

    with pytest.raises(ValueError):
        derive_deposit_address(mnemonic, chain_id=11_155_111, hd_index=0)
