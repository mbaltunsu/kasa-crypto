#!/usr/bin/env bash
# Stop the Kasa testnet stack (API + worker). Leaves Postgres and the frontend alone.
set -uo pipefail
LOG="${KASA_DEV_LOG:-/tmp/kasa-testnet}"
for p in api worker; do
  [ -f "$LOG/$p.pid" ] && kill "$(cat "$LOG/$p.pid")" 2>/dev/null
done
pkill -f "worker.main" 2>/dev/null
lsof -tiTCP:8000 -sTCP:LISTEN 2>/dev/null | xargs kill 2>/dev/null
echo "✓ testnet stack stopped (Postgres + frontend left running)"
