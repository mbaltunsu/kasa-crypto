from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bip_utils import Bip44 as Bip44Context

HOT_WALLET_INDEX = 0


@dataclass(frozen=True)
class DerivedAddress:
    address: str
    derivation_path: str


@dataclass(frozen=True)
class DerivedAccount:
    """A derived EVM account including its signing key (hot wallet / withdrawal signing)."""

    address: str
    private_key: str
    derivation_path: str


def _bip44_context(mnemonic: str, hd_index: int) -> Bip44Context:
    from bip_utils import Bip39SeedGenerator, Bip44, Bip44Changes, Bip44Coins

    seed = Bip39SeedGenerator(mnemonic).Generate("")
    return (
        Bip44.FromSeed(seed, Bip44Coins.ETHEREUM)
        .Purpose()
        .Coin()
        .Account(0)
        .Change(Bip44Changes.CHAIN_EXT)
        .AddressIndex(hd_index)
    )


def derive_evm_address(mnemonic: str, *, chain_id: int, hd_index: int) -> DerivedAddress:
    from eth_utils import to_checksum_address
    from kasa_shared.registry import derivation_path

    context = _bip44_context(mnemonic, hd_index)
    return DerivedAddress(
        address=to_checksum_address(context.PublicKey().ToAddress()),
        derivation_path=derivation_path(chain_id, hd_index),
    )


def derive_account(mnemonic: str, *, chain_id: int, hd_index: int) -> DerivedAccount:
    """Derive an EVM account with its raw private key. Key material is identical across EVM
    chains (coin type 60); only the derivation-path label differs by chain."""
    from eth_utils import to_checksum_address
    from kasa_shared.registry import derivation_path

    context = _bip44_context(mnemonic, hd_index)
    return DerivedAccount(
        address=to_checksum_address(context.PublicKey().ToAddress()),
        private_key="0x" + context.PrivateKey().Raw().ToHex(),
        derivation_path=derivation_path(chain_id, hd_index),
    )


def derive_hot_wallet(mnemonic: str, *, chain_id: int) -> DerivedAddress:
    return derive_evm_address(mnemonic, chain_id=chain_id, hd_index=HOT_WALLET_INDEX)


def hot_wallet_account(mnemonic: str, *, chain_id: int = 11_155_111) -> DerivedAccount:
    """The custodial hot wallet at m/44'/60'/0'/0/0 — pays withdrawals and gas."""
    return derive_account(mnemonic, chain_id=chain_id, hd_index=HOT_WALLET_INDEX)


def derive_deposit_address(mnemonic: str, *, chain_id: int, hd_index: int) -> DerivedAddress:
    if hd_index <= 0:
        msg = "user deposit hd_index must be positive; index 0 is reserved for the hot wallet"
        raise ValueError(msg)
    return derive_evm_address(mnemonic, chain_id=chain_id, hd_index=hd_index)
