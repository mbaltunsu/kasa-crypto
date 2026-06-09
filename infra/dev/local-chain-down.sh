#!/usr/bin/env bash
# Stop the local-Hardhat dev stack and restore the 31337 registry files deploy.ts mutated.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG="${KASA_DEV_LOG:-/tmp/kasa-dev}"
for p in api worker hardhat; do [ -f "$LOG/$p.pid" ] && kill "$(cat "$LOG/$p.pid")" 2>/dev/null; done
pkill -f "worker.main" 2>/dev/null
pkill -f "hardhat node" 2>/dev/null
lsof -tiTCP:8000 -sTCP:LISTEN 2>/dev/null | xargs kill 2>/dev/null
docker rm -f kasa-chain >/dev/null 2>&1
cd "$ROOT" && git checkout -- packages/shared/data/chains/31337.json packages/shared/deployments.json \
  packages/shared/src/_generated/registry.data.ts 2>/dev/null
echo "✓ local-chain dev stack down; 31337 registry restored."
