#!/usr/bin/env bash
# Persistent LOCAL-HARDHAT dev stack for REAL on-chain flows (mint / deposit / withdraw / sweep)
# without spending testnet funds. Starts: hardhat node (:8545, 2s interval mining) + deploys
# DEMO/KASA (owner = acct #0) + a fresh Postgres container (:5444) + API (:8000) + worker.
# Run the frontend separately (pnpm --filter frontend dev). Tear down with local-chain-down.sh.
#
# Uses the standard Hardhat TEST mnemonic (acct #0 = hot wallet) and DB :5444 — independent of .env.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

MNEMONIC="test test test test test test test test test test test junk"
RPC="http://127.0.0.1:8545"
CHAIN=31337
PG_CONTAINER="kasa-chain"
PG_PORT=5444
API_PORT=8000
LOG="${KASA_DEV_LOG:-/tmp/kasa-dev}"
mkdir -p "$LOG"

say(){ printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }
ok(){ printf '  \033[1;32m✓ %s\033[0m\n' "$*"; }
rpc(){ curl -s "$RPC" -H 'Content-Type: application/json' -d "$1"; }

say "0. stop any sim backend/worker on :$API_PORT"
lsof -tiTCP:$API_PORT -sTCP:LISTEN 2>/dev/null | xargs kill 2>/dev/null
pkill -f "worker.main" 2>/dev/null
pkill -f "hardhat node" 2>/dev/null
sleep 1

say "1. hardhat node ($CHAIN) with interval mining"
( cd contracts && exec pnpm hardhat node --hostname 127.0.0.1 ) > "$LOG/hardhat.log" 2>&1 &
echo $! > "$LOG/hardhat.pid"
for _ in $(seq 1 40); do rpc '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' 2>/dev/null | grep -q result && break; sleep 1; done
rpc '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' | grep -q result || { echo "hardhat failed"; tail "$LOG/hardhat.log"; exit 1; }
rpc '{"jsonrpc":"2.0","method":"evm_setIntervalMining","params":[2000],"id":1}' >/dev/null
ok "node up on $RPC, mining a block every 2s"

say "2. deploy DemoToken + DemoCollectible (hot wallet = acct #0 = owner)"
( cd contracts && pnpm hardhat run scripts/deploy.ts --network localhost ) > "$LOG/deploy.log" 2>&1 || { echo "deploy failed"; tail "$LOG/deploy.log"; exit 1; }
NFT_ADDR=$(python3 -c "import json;print(next(a['address'] for a in json.load(open('packages/shared/data/chains/$CHAIN.json'))['assets'] if a.get('symbol')=='KASA'))")
ok "DemoCollectible (KASA) @ $NFT_ADDR"

say "3. fresh postgres on :$PG_PORT"
docker rm -f "$PG_CONTAINER" >/dev/null 2>&1
docker run -d --name "$PG_CONTAINER" -e POSTGRES_USER=kasa -e POSTGRES_PASSWORD=kasa -e POSTGRES_DB=kasa -p "$PG_PORT:5432" postgres:16-alpine >/dev/null
for _ in $(seq 1 30); do docker exec "$PG_CONTAINER" pg_isready -U kasa >/dev/null 2>&1 && break; sleep 1; done
ok "postgres up"

export DATABASE_URL="postgresql+psycopg://kasa:kasa@127.0.0.1:$PG_PORT/kasa"
export JWT_SECRET="dev-secret" MASTER_MNEMONIC="$MNEMONIC" RPC_HARDHAT="$RPC"
export RPC_ETHEREUM_SEPOLIA="http://127.0.0.1:1" RPC_AVALANCHE_FUJI="http://127.0.0.1:1"
export FAUCET_PRIVATE_KEY="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
export MINT_ONCHAIN=1 DEPOSIT_CONFIRMATIONS=2 REORG_DEPTH=1 REORG_FINALITY_DEPTH=2
export WATCHER_POLL_SECONDS=1 WITHDRAWER_POLL_SECONDS=1 RESERVES_ONCHAIN=1
export RPC_MAX_RETRIES=1 RPC_REQUEST_TIMEOUT=2
export PYTHONPATH="$ROOT/backend:$ROOT/packages/shared/python"

say "4. alembic upgrade head (seeds assets incl 31337)"
( cd backend && uv run alembic upgrade head ) > "$LOG/migrate.log" 2>&1 || { echo "migrate failed"; tail "$LOG/migrate.log"; exit 1; }
ok "migrated + seeded"

say "5. backend (:$API_PORT) + worker"
( cd backend && exec uv run uvicorn --factory app.main:create_app --host 127.0.0.1 --port "$API_PORT" ) > "$LOG/api.log" 2>&1 &
echo $! > "$LOG/api.pid"
( cd backend && exec uv run python -m worker.main ) > "$LOG/worker.log" 2>&1 &
echo $! > "$LOG/worker.pid"
for _ in $(seq 1 40); do curl -s "http://127.0.0.1:$API_PORT/api/v1/health" 2>/dev/null | grep -q ok && break; sleep 1; done
curl -s "http://127.0.0.1:$API_PORT/api/v1/health" | grep -q ok || { echo "API not healthy"; tail "$LOG/api.log"; exit 1; }
ok "backend + worker up"

say "6. create users (alice=admin, bob=user; pw Password123!)"
B="http://127.0.0.1:$API_PORT/api/v1"
for u in alice bob; do
  curl -s -o /dev/null -X POST $B/auth/register -H 'Content-Type: application/json' -d "{\"email\":\"$u@kasa.dev\",\"password\":\"Password123!\"}"
done
docker exec "$PG_CONTAINER" psql -U kasa -d kasa -c "UPDATE users SET role='admin' WHERE email='alice@kasa.dev';" >/dev/null 2>&1
ok "alice@kasa.dev (admin) / bob@kasa.dev (user) — Password123!"

printf '\n\033[1;32m✅ Local-chain dev stack UP\033[0m\n'
echo "   api:    http://localhost:$API_PORT   (frontend: pnpm --filter frontend dev)"
echo "   chain:  $RPC (31337), KASA @ $NFT_ADDR"
echo "   logs:   $LOG/{hardhat,deploy,api,worker}.log"
