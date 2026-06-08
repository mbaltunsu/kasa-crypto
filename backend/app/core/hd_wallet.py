from dataclasses import dataclass


@dataclass(frozen=True)
class DerivedAddress:
    address: str
    derivation_path: str


def derive_evm_address(mnemonic: str, *, chain_id: int, hd_index: int) -> DerivedAddress:
    from bip_utils import Bip39SeedGenerator, Bip44, Bip44Changes, Bip44Coins
    from eth_utils import to_checksum_address
    from kasa_shared.registry import derivation_path

    path = derivation_path(chain_id, hd_index)
    seed = Bip39SeedGenerator(mnemonic).Generate("")
    context = (
        Bip44.FromSeed(seed, Bip44Coins.ETHEREUM)
        .Purpose()
        .Coin()
        .Account(0)
        .Change(Bip44Changes.CHAIN_EXT)
        .AddressIndex(hd_index)
    )
    return DerivedAddress(
        address=to_checksum_address(context.PublicKey().ToAddress()),
        derivation_path=path,
    )


def derive_hot_wallet(mnemonic: str, *, chain_id: int) -> DerivedAddress:
    return derive_evm_address(mnemonic, chain_id=chain_id, hd_index=0)


def derive_deposit_address(mnemonic: str, *, chain_id: int, hd_index: int) -> DerivedAddress:
    if hd_index <= 0:
        msg = "user deposit hd_index must be positive; index 0 is reserved for the hot wallet"
        raise ValueError(msg)
    return derive_evm_address(mnemonic, chain_id=chain_id, hd_index=hd_index)
