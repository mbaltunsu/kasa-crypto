from enum import IntEnum, StrEnum


class ChainId(IntEnum):
    ETHEREUM_SEPOLIA = 11_155_111
    AVALANCHE_FUJI = 43_113


class AssetType(StrEnum):
    NATIVE = "native"
    ERC20 = "erc20"
    ERC721 = "erc721"


EVM_COIN_TYPE = 60
NATIVE_ASSET_SENTINEL = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
