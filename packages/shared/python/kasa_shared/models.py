from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from kasa_shared.consts import AssetType


class NativeAsset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal[AssetType.NATIVE]
    symbol: str
    name: str
    decimals: int


class Erc20Asset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal[AssetType.ERC20]
    symbol: str
    name: str
    decimals: int
    address: str
    deployment_block: int = Field(alias="deploymentBlock")


class Erc721Asset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal[AssetType.ERC721]
    symbol: str
    name: str
    decimals: Literal[0]
    address: str
    deployment_block: int = Field(alias="deploymentBlock")


Asset = Annotated[NativeAsset | Erc20Asset | Erc721Asset, Field(discriminator="type")]


class Chain(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    chain_id: int = Field(alias="chainId")
    name: str
    display_name: str = Field(alias="displayName")
    native_symbol: str = Field(alias="nativeSymbol")
    coin_type: int = Field(alias="coinType")
    rpc_env: str = Field(alias="rpcEnv")
    explorer_tx_url: str = Field(alias="explorerTxUrl")
    explorer_address_url: str = Field(alias="explorerAddressUrl")
    assets: tuple[Asset, ...]
