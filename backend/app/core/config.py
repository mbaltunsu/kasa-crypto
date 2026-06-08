from functools import lru_cache

from pydantic import AliasChoices
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(alias="DATABASE_URL")
    jwt_secret: str = Field(alias="JWT_SECRET")
    access_ttl_seconds: int = Field(
        default=900,
        validation_alias=AliasChoices("ACCESS_TTL_SECONDS", "ACCESS_TOKEN_TTL_SECONDS"),
    )
    refresh_ttl_seconds: int = Field(
        default=2_592_000,
        validation_alias=AliasChoices("REFRESH_TTL_SECONDS", "REFRESH_TOKEN_TTL_SECONDS"),
    )
    master_mnemonic: str = Field(alias="MASTER_MNEMONIC")
    rpc_ethereum_sepolia: str = Field(alias="RPC_ETHEREUM_SEPOLIA")
    rpc_avalanche_fuji: str = Field(alias="RPC_AVALANCHE_FUJI")
    deposit_confirmations: int = Field(default=12, alias="DEPOSIT_CONFIRMATIONS")
    frontend_origin: str = Field(default="http://localhost:3000", alias="FRONTEND_ORIGIN")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
