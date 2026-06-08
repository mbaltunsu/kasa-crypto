# Kasa — Custodial Multi-Chain Exchange Wallet

A runnable miniature of what a crypto exchange does end-to-end: users get a unique on-chain
deposit address, deposits are indexed and credited to a **double-entry ledger**, balances are
spendable via internal transfers (instant, no gas) or on-chain withdrawals signed from a hot
wallet — across **Ethereum Sepolia** and **Avalanche Fuji**, with **verified** ERC-20 + ERC-721
contracts on the explorers.

> Portfolio build. The README documents what production would do differently (KMS/HSM keys,
> withdrawal approvals, cold-storage sweeps) — knowing the gap is part of the signal.

**Live demo:** _(added at deploy)_ · **Verified contracts:** _(Etherscan / Snowtrace links added at deploy)_

---

## JD coverage map

| Requirement | How Kasa demonstrates it |
|---|---|
| Python back-end | FastAPI API + Python worker processes |
| Solidity | `DemoToken` (ERC-20) + `DemoCollectible` (ERC-721), tested |
| web3 | `web3.py` for reads, event watching, signing, broadcast |
| Relational DB design | Postgres: double-entry ledger, idempotent indexing, block cursors |
| OOP / event-driven / distributed | Service classes; event watcher; separate worker; `SKIP LOCKED` queue; per-chain cursors |
| ERC-20 + ERC-721 standards | Both authored, deployed, **verified** on Etherscan/Snowtrace |
| Cryptography | BIP-32/39/44 derivation, ECDSA signing, password hashing, JWT |
| BIP-32/39/44 (plus) | One master seed → per-user deposit addresses + hot wallet |
| MVC + RESTful | routers = controllers, services = domain, models = data; REST API |
| Multi-chain (ETH, Avalanche) | Sepolia + Fuji; Bitcoin documented as a stretch |

---

## Architecture (at a glance)

Three processes sharing one Postgres (no external broker — jobs use `SELECT … FOR UPDATE SKIP LOCKED`):

1. **API** (FastAPI, stateless) — auth, balances, deposit addresses, withdrawals, transfers, admin, faucet.
2. **Watcher / indexer** — per-chain scan from `last_scanned_block` for ERC-20 `Transfer` logs + direct
   native deposits → idempotent `onchain_deposits` → credits the ledger after N confirmations (reorg-safe).
3. **Withdrawal processor** — `SKIP LOCKED` queue, one serialized worker per chain, hot-wallet nonce table,
   sign + broadcast + confirm, reverse on failure.

A single BIP-39 master mnemonic derives a hot wallet (`m/44'/60'/0'/0/0`) and a unique deposit address per
user (`m/44'/60'/0'/0/{hd_index}`) — same address across EVM chains, as is realistic.

Full design in [docs/architecture.md](docs/architecture.md). API contract in
[docs/api_architecture.md](docs/api_architecture.md). Data model in [docs/db_model.md](docs/db_model.md).
Cross-language types + chain/token registry in [docs/types_and_registry.md](docs/types_and_registry.md).

```
kasa/
├── contracts/        # Hardhat + Solidity (ERC-20 + ERC-721), TS deploy
├── backend/          # Python / FastAPI + SQLAlchemy/Alembic + workers (uv)
├── frontend/         # Next.js + Tailwind (TS), typed client codegen'd from OpenAPI
├── packages/shared/  # chain/token/NFT registry — one source of truth, TS + Python consumers
├── infra/            # docker-compose, e2e script
└── docs/             # architecture / api / db / types coordination docs
```

---

## Quickstart

```bash
cp .env.example .env        # dev defaults work out of the box (Hardhat test mnemonic)
make install                # pnpm + uv
make up                     # postgres + hardhat-node + backend + worker + frontend
# open http://localhost:3000
```

Then run the full cycle:

```bash
make e2e                    # register → get address → simulate deposit → watcher credits → withdraw → confirmed
make test                   # contracts + shared + backend suites
```

---

## Security notes (what production would change)

The demo holds keys in an env-var mnemonic + a single hot wallet. Production would use KMS/HSM-held keys
encrypted at rest, withdrawal approval workflows + limits, cold-storage sweeps, tuned reorg depth, rate
limiting, and 2FA. These are documented as stretch items, not silently dropped.

---

## Tech

Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic · web3.py · Pydantic v2 · Postgres 16 ·
Solidity + Hardhat + OpenZeppelin · Next.js + TypeScript + Tailwind · pnpm workspaces · uv · Docker Compose.
