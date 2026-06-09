#!/usr/bin/env bash
# Run the Kasa stack against the LIVE testnets (Sepolia + Fuji) using the repo-root .env.
# Starts the API (:8000) and the chain worker against the local dev Postgres on :5433;
# run the frontend separately with `pnpm --filter frontend dev`.
#
# Prereqs: a Postgres reachable at $DATABASE_URL (the repo uses a docker container on :5433),
# migrated to head (cd backend && alembic upgrade head), and a funded hot wallet in .env.
# Tear down with infra/dev/testnet-down.sh
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG="${KASA_DEV_LOG:-/tmp/kasa-testnet}"
mkdir -p "$LOG"

# Load testnet env (tolerate any bare unquoted lines; the app reads MASTER_MNEMONIC etc.).
set -a; source "$ROOT/.env" 2>/dev/null || true; set +a
# Snappier demo: credit deposits after 3 confs instead of the .env default.
export DEPOSIT_CONFIRMATIONS="${DEPOSIT_CONFIRMATIONS_OVERRIDE:-3}"
# No local Hardhat node on a testnet run — empty its RPC so chain 31337 is skipped everywhere.
export RPC_HARDHAT=""
export PYTHONPATH="$ROOT/backend:$ROOT/packages/shared/python"

echo "DATABASE_URL=$DATABASE_URL  DEPOSIT_CONFIRMATIONS=$DEPOSIT_CONFIRMATIONS  MINT_ONCHAIN=${MINT_ONCHAIN:-}"

cd "$ROOT/backend"
( exec uv run uvicorn --factory app.main:create_app --host 127.0.0.1 --port 8000 ) > "$LOG/api.log" 2>&1 &
echo $! > "$LOG/api.pid"
( exec uv run python -m worker.main ) > "$LOG/worker.log" 2>&1 &
echo $! > "$LOG/worker.pid"

for _ in $(seq 1 60); do
  curl -s http://127.0.0.1:8000/api/v1/health 2>/dev/null | grep -q ok && break
  sleep 1
done
echo "--- health ---"; curl -s http://127.0.0.1:8000/api/v1/health || echo "(API not responding)"
echo
echo "API :8000 + worker up. logs: $LOG/{api,worker}.log   frontend: pnpm --filter frontend dev"
