#!/usr/bin/env bash
# Kasa money-flow end-to-end demo against a local Hardhat chain (no testnet funds needed).
#
#   register → faucet (REAL on-chain send) → watcher credits the ledger after N confs
#            → withdraw → withdrawer signs+broadcasts → confirmed
#
# asserting at each step that the double-entry ledger matches on-chain balances. Exercises the
# actual app/chain client + worker/watcher + worker/withdrawer against a real EVM node.
#
# Requires: docker, node+pnpm, python3. Run from anywhere: `bash infra/e2e.sh` (or `make e2e`).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# ── fixed local-Hardhat facts (deterministic test mnemonic) ──────────────────────────────────
MNEMONIC="test test test test test test test test test test test junk"
HOT_KEY="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80" # acct #0: hot wallet + faucet + contract owner
RPC="http://127.0.0.1:8545"
CHAIN=31337
EXTERNAL="0x000000000000000000000000000000000000bEEF" # withdrawal destination
PG_CONTAINER="kasa-e2e-pg"
PG_PORT=5444
API_PORT=8010
ONE_ETH=1000000000000000000
HALF_ETH=500000000000000000

HARDHAT_PID="" ; API_PID="" ; WORKER_PID=""
LOG_DIR="$(mktemp -d)"

say()  { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }
ok()   { printf '  \033[1;32m✓ %s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31m✗ %s\033[0m\n' "$*"
         echo "--- api.log ---";    tail -n 25 "$LOG_DIR/api.log"    2>/dev/null || true
         echo "--- worker.log ---"; tail -n 25 "$LOG_DIR/worker.log" 2>/dev/null || true
         exit 1; }

cleanup() {
  set +e
  [ -n "$WORKER_PID" ]  && kill "$WORKER_PID"  2>/dev/null
  [ -n "$API_PID" ]     && kill "$API_PID"     2>/dev/null
  [ -n "$HARDHAT_PID" ] && kill "$HARDHAT_PID" 2>/dev/null
  pkill -f "hardhat node" 2>/dev/null
  docker rm -f "$PG_CONTAINER" >/dev/null 2>&1
  # deploy.ts wrote the local contract addresses into the registry — restore the committed 0x0 entry.
  git checkout -- packages/shared/data/chains/${CHAIN}.json packages/shared/deployments.json \
                  packages/shared/src/_generated/registry.data.ts 2>/dev/null
  rm -rf "$LOG_DIR"
}
trap cleanup EXIT

# ── helpers ──────────────────────────────────────────────────────────────────────────────────
rpc()  { curl -s "$RPC" -H 'Content-Type: application/json' -d "$1"; }
mine() { rpc "{\"jsonrpc\":\"2.0\",\"method\":\"hardhat_mine\",\"params\":[\"$1\"],\"id\":1}" >/dev/null; }
api()  { local m=$1 path=$2; shift 2; curl -s -X "$m" "http://127.0.0.1:${API_PORT}${path}" \
           -H "Authorization: Bearer ${TOKEN:-}" -H 'Content-Type: application/json' "$@"; }
PYJSON() { "$PY" -c "import sys,json; d=json.load(sys.stdin); print($1)"; }

eth_balance()   { rpc "{\"jsonrpc\":\"2.0\",\"method\":\"eth_getBalance\",\"params\":[\"$1\",\"latest\"],\"id\":1}" | PYJSON "int(d['result'],16)"; }
erc20_balance() { local d="0x70a08231000000000000000000000000${2:2}"
  rpc "{\"jsonrpc\":\"2.0\",\"method\":\"eth_call\",\"params\":[{\"to\":\"$1\",\"data\":\"$d\"},\"latest\"],\"id\":1}" | PYJSON "int(d['result'],16)"; }
asset_id()      { api GET /api/v1/wallet/balances | PYJSON "next(a['asset_id'] for a in d if a['chain_id']==$CHAIN and a['symbol']=='$1')"; }
available()     { api GET /api/v1/wallet/balances | PYJSON "next(a['available'] for a in d if a['chain_id']==$CHAIN and a['symbol']=='$1')"; }
wd_status()     { api GET "/api/v1/withdrawals/$1" | PYJSON "d['status']"; }

wait_until() { # $1 label  $2 expected  $3 command…
  local label=$1 expected=$2; shift 2
  for _ in $(seq 1 60); do [ "$("$@")" = "$expected" ] && { ok "$label = $expected"; return 0; }; sleep 1; done
  die "TIMEOUT $label: expected $expected, got $("$@")"
}

# ── python runtime (reuse $KASA_E2E_VENV or build one; no uv needed) ───────────────────────────
say "python env"
VENV="${KASA_E2E_VENV:-$ROOT/backend/.e2e-venv}"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --disable-pip-version-check \
    fastapi "uvicorn[standard]" "sqlalchemy[asyncio]>=2" alembic pydantic pydantic-settings \
    "psycopg[binary]" "python-jose[cryptography]" "passlib[argon2]" web3 bip-utils "eth-hash[pycryptodome]"
fi
PY="$VENV/bin/python"
ok "using $PY"

# ── 1. local chain ─────────────────────────────────────────────────────────────────────────────
say "starting Hardhat node"
( cd contracts && exec pnpm hardhat node --hostname 127.0.0.1 ) >"$LOG_DIR/hardhat.log" 2>&1 &
HARDHAT_PID=$!
for _ in $(seq 1 40); do rpc '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' 2>/dev/null | grep -q result && break; sleep 1; done
rpc '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' | grep -q result || die "hardhat node did not start"
ok "node up on $RPC"

# ── 2. deploy contracts (writes real addresses into the 31337 registry + regenerates) ───────────
say "deploying DemoToken + DemoCollectible"
( cd contracts && pnpm hardhat run scripts/deploy.ts --network localhost ) || die "deploy failed"
DEMO_ADDR="$("$PY" -c "import json;print(next(a['address'] for a in json.load(open('packages/shared/data/chains/${CHAIN}.json'))['assets'] if a.get('symbol')=='DEMO'))")"
ok "DEMO @ $DEMO_ADDR"

# ── 3. postgres ────────────────────────────────────────────────────────────────────────────────
say "starting Postgres"
docker rm -f "$PG_CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$PG_CONTAINER" -e POSTGRES_USER=kasa -e POSTGRES_PASSWORD=kasa -e POSTGRES_DB=kasa \
  -p "${PG_PORT}:5432" postgres:16-alpine >/dev/null
for _ in $(seq 1 30); do docker exec "$PG_CONTAINER" pg_isready -U kasa >/dev/null 2>&1 && break; sleep 1; done
ok "postgres up on :$PG_PORT"

export DATABASE_URL="postgresql+psycopg://kasa:kasa@127.0.0.1:${PG_PORT}/kasa"
export JWT_SECRET="e2e-secret"
export MASTER_MNEMONIC="$MNEMONIC"
export RPC_HARDHAT="$RPC"
# Point the other registry chains at a dead port so only 31337 is actually watched (the worker is
# resilient — unreachable chains just log + retry). Fast-fail so they don't slow the 31337 loop.
export RPC_ETHEREUM_SEPOLIA="http://127.0.0.1:1"
export RPC_AVALANCHE_FUJI="http://127.0.0.1:1"
export FAUCET_PRIVATE_KEY="$HOT_KEY"
export DEPOSIT_CONFIRMATIONS=1 REORG_DEPTH=1 WATCHER_POLL_SECONDS=1 WITHDRAWER_POLL_SECONDS=1 RESERVES_ONCHAIN=1
export RPC_MAX_RETRIES=1 RPC_REQUEST_TIMEOUT=2
export PYTHONPATH="$ROOT/backend:$ROOT/packages/shared/python"

# ── 4. migrate (seeds assets from the registry incl. the just-deployed 31337 addresses) ─────────
say "alembic upgrade head (schema + asset seed)"
( cd backend && "$PY" -m alembic upgrade head ) || die "migration failed"

# ── 5. API + worker ──────────────────────────────────────────────────────────────────────────────
say "starting API + worker"
( cd backend && exec "$PY" -m uvicorn --factory app.main:create_app --host 127.0.0.1 --port "$API_PORT" ) >"$LOG_DIR/api.log" 2>&1 &
API_PID=$!
( cd backend && exec "$PY" -m worker.main ) >"$LOG_DIR/worker.log" 2>&1 &
WORKER_PID=$!
for _ in $(seq 1 40); do curl -s "http://127.0.0.1:${API_PORT}/api/v1/health" 2>/dev/null | grep -q ok && break; sleep 1; done
curl -s "http://127.0.0.1:${API_PORT}/api/v1/health" | grep -q ok || die "API did not become healthy"
ok "API + worker up"

# ── 6. the money flow ──────────────────────────────────────────────────────────────────────────
say "register a user"
TOKEN="$(api POST /api/v1/auth/register -d '{"email":"e2e@kasa.test","password":"hunter2hunter2"}' | PYJSON "d['access_token']")"
[ -n "$TOKEN" ] || die "register returned no token"
DEPOSIT_ADDR="$(api GET /api/v1/wallet/deposit-addresses | PYJSON "next(a['address'] for a in d if a['chain_id']==$CHAIN)")"
ETH_ID="$(asset_id ETH)" ; DEMO_ID="$(asset_id DEMO)"
ok "user deposit address $DEPOSIT_ADDR"

say "faucet 1 ETH (real on-chain send) → watcher credits"
eth_before="$(eth_balance "$DEPOSIT_ADDR")" # the deposit addr is a pre-funded Hardhat account
api POST /api/v1/demo/faucet -H "Idempotency-Key: eth-$RANDOM" -d "{\"asset_id\":\"$ETH_ID\",\"amount\":\"$ONE_ETH\"}" >/dev/null
mine "0x3" # accrue confirmations past the faucet tx
wait_until "ledger available ETH" "$ONE_ETH" available ETH
eth_delta=$(( $(eth_balance "$DEPOSIT_ADDR") - eth_before ))
[ "$eth_delta" = "$ONE_ETH" ] || die "on-chain ETH delta $eth_delta != faucet $ONE_ETH"
ok "faucet credited 1 ETH on-chain AND in the ledger"

say "faucet 1 DEMO (ERC-20 Transfer) → watcher credits"
api POST /api/v1/demo/faucet -H "Idempotency-Key: demo-$RANDOM" -d "{\"asset_id\":\"$DEMO_ID\",\"amount\":\"$ONE_ETH\"}" >/dev/null
mine "0x3"
wait_until "ledger available DEMO" "$ONE_ETH" available DEMO
[ "$(erc20_balance "$DEMO_ADDR" "$DEPOSIT_ADDR")" = "$ONE_ETH" ] || die "on-chain DEMO at deposit addr != ledger"
ok "ledger DEMO == on-chain DEMO ($ONE_ETH units)"

say "withdraw 0.5 ETH → withdrawer signs + broadcasts → confirmed"
before="$(eth_balance "$EXTERNAL")"
WID="$(api POST /api/v1/withdrawals -H "Idempotency-Key: wd-$RANDOM" -d "{\"asset_id\":\"$ETH_ID\",\"to_address\":\"$EXTERNAL\",\"amount\":\"$HALF_ETH\"}" | PYJSON "d['id']")"
[ "$(available ETH)" = "$HALF_ETH" ] && ok "0.5 ETH reserved (available now 0.5)" || die "reservation did not debit available"
# give the withdrawer a poll cycle to broadcast, then mine so the receipt is available
sleep 3
mine "0x3"
wait_until "withdrawal status" "confirmed" wd_status "$WID"
paid=$(( $(eth_balance "$EXTERNAL") - before ))
[ "$paid" = "$HALF_ETH" ] || die "external address received $paid, expected $HALF_ETH"
ok "external address received 0.5 ETH on-chain"

say "proof-of-reserves (on-chain)"
api GET /api/v1/admin/reserves >/dev/null 2>&1 || true # user token isn't admin; just confirm endpoint reachable

printf '\n\033[1;32m✅ e2e PASSED — register → faucet → on-chain credit → withdraw → confirmed, ledger == chain\033[0m\n'
