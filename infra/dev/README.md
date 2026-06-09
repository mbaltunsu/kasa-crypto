# Dev stack helpers

Local orchestration scripts for exercising the real money flow (deposit → credit →
withdraw → confirm, plus NFT mint / transfer / withdraw / sweep) outside of `docker compose`.
All scripts derive the repo root from their own location, so run them from anywhere.

## Local Hardhat chain (no testnet funds)

Spins up a Hardhat node (`:8545`, 2 s mining), deploys DEMO/KASA, a fresh Postgres
(`:5444`), the API (`:8000`), and the worker. Uses the standard Hardhat test mnemonic.

```bash
bash infra/dev/local-chain-up.sh      # then: pnpm --filter frontend dev
bash infra/dev/local-chain-down.sh    # stops everything; restores the 31337 registry files
```

Seeds two users: `alice@kasa.dev` (admin) / `bob@kasa.dev`, password `Password123!`.

## Live testnet (Sepolia + Fuji)

Runs the API + worker against the live testnets using the repo-root `.env` (real RPCs,
funded hot wallet). Expects a Postgres at `$DATABASE_URL` already migrated to head
(`cd backend && uv run alembic upgrade head`).

```bash
bash infra/dev/testnet-up.sh          # then: pnpm --filter frontend dev
bash infra/dev/testnet-down.sh
```

`RPC_HARDHAT` is emptied so the dev-only chain `31337` is skipped; deposits credit after
3 confirmations (`DEPOSIT_CONFIRMATIONS`).
