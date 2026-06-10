from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Maps registry chain ids to the settings field holding their (comma-separated) RPC URL list.
_RPC_FIELD_BY_CHAIN: dict[int, str] = {
    11_155_111: "rpc_ethereum_sepolia",
    43_113: "rpc_avalanche_fuji",
    31_337: "rpc_hardhat",
}


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
    rpc_hardhat: str = Field(default="http://localhost:8545", alias="RPC_HARDHAT")
    deposit_confirmations: int = Field(default=12, alias="DEPOSIT_CONFIRMATIONS")
    frontend_origin: str = Field(default="http://localhost:3000", alias="FRONTEND_ORIGIN")

    # ── Chain workers (watcher + withdrawal processor) ─────────────────────────────
    faucet_private_key: str | None = Field(default=None, alias="FAUCET_PRIVATE_KEY")
    reorg_depth: int = Field(default=5, alias="REORG_DEPTH")
    # Keep a credited deposit reversible for this many blocks past its credit point (a chain's
    # practical finality depth), not merely `reorg_depth` blocks (finding #13).
    reorg_finality_depth: int = Field(default=64, alias="REORG_FINALITY_DEPTH")
    block_chunk_size: int = Field(default=2_000, alias="BLOCK_CHUNK_SIZE")
    # Opt-in: also index native deposits delivered via contract internal calls (#11). Needs a
    # trace-capable RPC (debug_traceBlockByNumber); off by default and a no-op without one.
    watch_internal_transfers: bool = Field(default=False, alias="WATCH_INTERNAL_TRANSFERS")
    watcher_poll_seconds: float = Field(default=10.0, alias="WATCHER_POLL_SECONDS")
    withdrawer_poll_seconds: float = Field(default=10.0, alias="WITHDRAWER_POLL_SECONDS")
    rpc_max_retries: int = Field(default=3, alias="RPC_MAX_RETRIES")
    rpc_request_timeout: float = Field(default=20.0, alias="RPC_REQUEST_TIMEOUT")
    # Proof-of-reserves reads live balances off-chain only when explicitly enabled (needs reachable
    # RPC); otherwise the admin report stays fast and uses ledger liabilities as the reserve figure.
    reserves_onchain: bool = Field(default=False, alias="RESERVES_ONCHAIN")
    # Admin NFT minting uses the real on-chain outbox only when explicitly enabled. Otherwise it
    # writes simulated holdings directly so the demo works offline.
    mint_onchain: bool = Field(default=False, alias="MINT_ONCHAIN")
    rate_limit_enabled: bool = Field(default=True, alias="RATE_LIMIT_ENABLED")
    gas_warn_wei: int = Field(default=20_000_000_000_000_000, alias="GAS_WARN_WEI")
    gas_critical_wei: int = Field(default=5_000_000_000_000_000, alias="GAS_CRITICAL_WEI")

    # Demo convenience: seed a known login at startup (off by default; the login form prefills it).
    seed_demo_user: bool = Field(default=False, alias="SEED_DEMO_USER")
    demo_email: str = Field(default="demo@kasa.app", alias="DEMO_EMAIL")
    demo_password: str = Field(default="kasademo123", alias="DEMO_PASSWORD")

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        # Managed Postgres (Railway/Render/Heroku/Fly) hands out `postgres://` or `postgresql://`;
        # the app + Alembic both run on the async psycopg driver, so normalize the scheme once here
        # (idempotent — leaves an already-qualified `postgresql+psycopg`/`+asyncpg` URL untouched).
        if value.startswith(("postgresql+", "postgres+")):
            return value
        if value.startswith("postgresql://"):
            return "postgresql+psycopg://" + value[len("postgresql://") :]
        if value.startswith("postgres://"):
            return "postgresql+psycopg://" + value[len("postgres://") :]
        return value

    def rpc_urls(self, chain_id: int) -> list[str]:
        field = _RPC_FIELD_BY_CHAIN.get(chain_id)
        if field is None:
            msg = f"no RPC configured for chain {chain_id}"
            raise KeyError(msg)
        raw: str = getattr(self, field)
        return [url.strip() for url in raw.split(",") if url.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
