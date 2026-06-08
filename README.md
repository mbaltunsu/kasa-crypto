# 🏦 Kasa — Custodial Multi-Chain Exchange Wallet

A runnable miniature of what a crypto exchange does end‑to‑end: every user gets a unique on‑chain
**deposit address**, deposits are **indexed and credited to a double‑entry ledger**, and balances are
spendable via **instant internal transfers** (no gas) or **on‑chain withdrawals** signed from a hot
wallet — across **Ethereum Sepolia** and **Avalanche Fuji**, with **verified** ERC‑20 + ERC‑721
contracts on the explorers.

![backend](https://img.shields.io/badge/backend-60_tests_passing-brightgreen)
![shared](https://img.shields.io/badge/shared_registry-37_tests_passing-brightgreen)
![contracts](https://img.shields.io/badge/contracts-6_tests_passing-brightgreen)
![types](https://img.shields.io/badge/mypy-strict-blue)
![e2e](https://img.shields.io/badge/e2e-on--chain_✓-success)
![chains](https://img.shields.io/badge/chains-Sepolia_+_Fuji-8A2BE2)

> 🎯 **Portfolio build** for a Blockchain Developer role. It deliberately documents what production
> would do differently (KMS/HSM keys, withdrawal approvals, cold‑storage sweeps) — *knowing the gap is
> part of the signal.*

---

## ✅ Live on testnets — deployed & verified contracts

| Chain | Contract | Address | Explorer |
|---|---|---|---|
| 🟣 Ethereum Sepolia | `DemoToken` (ERC‑20) | `0x15fe2D2D221F2B3Ee96D230d50B496Ab5F1b8B3E` | [Etherscan ✓](https://sepolia.etherscan.io/address/0x15fe2D2D221F2B3Ee96D230d50B496Ab5F1b8B3E#code) |
| 🟣 Ethereum Sepolia | `DemoCollectible` (ERC‑721) | `0x88F67A2EbD4C342496d0A477EF58F3a89BCF95F2` | [Etherscan ✓](https://sepolia.etherscan.io/address/0x88F67A2EbD4C342496d0A477EF58F3a89BCF95F2#code) |
| 🔺 Avalanche Fuji | `DemoToken` (ERC‑20) | `0x4dBD859993952132Be0499CEF34419fc1A604867` | [Snowtrace ✓](https://testnet.snowtrace.io/address/0x4dBD859993952132Be0499CEF34419fc1A604867#code) |
| 🔺 Avalanche Fuji | `DemoCollectible` (ERC‑721) | `0xF83a0306A284A9AF72464D58b63501a55c846873` | [Snowtrace ✓](https://testnet.snowtrace.io/address/0xF83a0306A284A9AF72464D58b63501a55c846873#code) |

The full app runs locally with one command (`make up`); the end‑to‑end money flow is reproducible
on a local chain with `make e2e` (see [Quickstart](#-quickstart)).

---

## 🗺️ JD coverage map

| Requirement | How Kasa demonstrates it |
|---|---|
| **Python back‑end** | FastAPI API + an asyncio worker process (watcher + withdrawal processor) |
| **Solidity** | `DemoToken` (ERC‑20) + `DemoCollectible` (ERC‑721), unit‑tested |
| **web3** | `web3.py` for reads, event log scanning, signing, broadcast, receipts |
| **Relational DB design** | Postgres: double‑entry ledger, idempotent indexing, per‑chain block cursors |
| **OOP / event‑driven / distributed** | Service classes; event watcher; separate worker; `SKIP LOCKED` job queue; per‑chain cursors |
| **ERC‑20 + ERC‑721** | Both authored, deployed, **verified** on Etherscan/Snowtrace (above) |
| **Cryptography** | BIP‑32/39/44 derivation, ECDSA signing, Argon2 password hashing, JWT |
| **BIP‑32/39/44** | One master seed → per‑user deposit addresses + a hot wallet |
| **MVC + RESTful** | routers = controllers, services = domain, models = data; clean REST surface |
| **Multi‑chain (ETH, Avalanche)** | Sepolia + Fuji from one registry; a local Hardhat chain for the e2e |

---

## 🏗️ Architecture

Three processes sharing one Postgres — **no external broker**; job queues use
`SELECT … FOR UPDATE SKIP LOCKED`.

```
                 ┌──────────────┐        ┌────────────────────────────────┐
   browser ────► │ API (FastAPI)│ ─────► │            Postgres            │
                 │  stateless   │ ◄───── │  users · assets · ledger_*     │
                 └──────────────┘        │  onchain_deposits · withdrawals│
                                         │  chain_cursors · hot_wallet_*  │
   testnet  ┌───────────────────┐        │  (jobs: … SKIP LOCKED)         │
   RPCs ◄──►│ Watcher / indexer │ ──────►│                                │
            │ (per chain)       │        └────────────────────────────────┘
            └───────────────────┘                   ▲
   testnet  ┌───────────────────────┐               │
   RPCs ◄──►│ Withdrawal processor  │ ──────────────┘
            │ (1 serialized / chain)│
            └───────────────────────┘
```

1. **API** (FastAPI, stateless) — auth, balances, deposit addresses, withdrawals, transfers, admin, faucet.
2. **Watcher / indexer** — per‑chain scan from `last_scanned_block` for ERC‑20 `Transfer` logs + native
   deposits → **idempotent** `onchain_deposits` → credits the ledger after _N_ confirmations, **re‑validating
   the block hash** and reversing on reorg.
3. **Withdrawal processor** — `SKIP LOCKED` queue, **one serialized worker per chain**, a persisted
   hot‑wallet nonce table, sign → broadcast → confirm, reverse the reservation on failure.

A single BIP‑39 master mnemonic derives a hot wallet (`m/44'/60'/0'/0/0`) and a unique deposit address per
user (`m/44'/60'/0'/0/{hd_index}`) — the **same address across EVM chains**, as is realistic.

### 🔒 Two “no‑drift” seams (one master per concern, everything else generated + CI‑gated)

- **Registry seam** — chains/tokens/NFTs live in `packages/shared/data`; a pinned **content hash**
  (TS `canonicalRows` ≡ Python `content_hash`) gates cross‑language parity, and the DB asset seed is
  derived from the same source.
- **API‑type seam** — backend Pydantic models + `StrEnum`s → `openapi.json` → the frontend’s typed
  `openapi‑fetch` client. The wire types are generated, never hand‑written.

Deeper design: [architecture](docs/architecture.md) · [API](docs/api_architecture.md) ·
[data model](docs/db_model.md) · [types & registry](docs/types_and_registry.md) ·
[decisions log](docs/decisions.md).

---

## 💸 The money flow (what `make e2e` proves on a real chain)

```
register ─► faucet (REAL on‑chain ETH + ERC‑20 send)
         ─► watcher detects + credits the ledger after confirmations
         ─► withdraw ─► withdrawer signs + broadcasts ─► confirmed
```

…asserting the **double‑entry ledger == on‑chain balances** at every step, against a local Hardhat node
(no testnet funds required). It exercises the real `web3.py` client, watcher, and withdrawal processor.

### 🛡️ Correctness & safety properties (enforced + tested)

- **Double‑entry ledger** — every transaction posts entries that **sum to zero per asset** and is
  **idempotent** on an idempotency key; balances are *summed*, never a mutable column.
- **Reorg‑safe deposits** — credit only after _N_ confs *and* a block‑hash re‑check; a reorg orphans the
  deposit, **reverses the credit**, rewinds the cursor, and re‑credits the re‑mined tx.
- **Custody‑safe withdrawals** — a broadcast that the node already accepted is **never falsely reversed**
  (the client classifies “already known” / verifies the tx on‑chain), and nonces are gap‑free.
- **Amounts** — integer base units, **string on the wire, never float**; the identical pure‑string
  algorithm in TS and Python is proven by a shared golden‑vector corpus.
- **Addresses** — stored EIP‑55 checksummed, compared lowercase.

These weren’t free: a multi‑agent adversarial review of the worker hardened **14 real findings**
(custody‑loss on lost broadcast, reorg edge cases, faucet idempotency), and the on‑chain e2e caught a
Postgres‑only `Decimal` serialization bug the SQLite unit tests missed.

---

## 🚀 Quickstart

```bash
cp .env.example .env        # dev defaults work out of the box (Hardhat test mnemonic + public RPCs)
make install                # pnpm workspaces + Python (uv)
make up                     # postgres → migrate → backend + worker + frontend  (http://localhost:3000)
```

Reproduce the full on‑chain cycle and run every test suite:

```bash
make e2e                    # local Hardhat: register → faucet → watcher credits → withdraw → confirmed
make test                   # contracts (Hardhat) + shared registry (vitest) + backend (pytest)
make lint                   # ruff + mypy (strict) + tsc
```

> `make up` boots the whole stack from Docker images (the backend image serves **both** the API and the
> worker; a one‑shot `migrate` service runs Alembic before either starts).

---

## 🧪 Verification status

| Suite | Result |
|---|---|
| Backend (pytest, mocked‑web3, no network) | **60 passing** |
| Shared registry (vitest, incl. cross‑language parity) | **37 passing** |
| Contracts (Hardhat) | **6 passing** |
| Types | **mypy `--strict` clean** across 78 files |
| End‑to‑end (`make e2e`, real local chain) | **green** |
| Contracts on Sepolia + Fuji | **deployed & verified** |

---

## 📁 Repository layout

```
kasa/
├── contracts/        # Hardhat + Solidity (ERC-20 + ERC-721) + TS deploy/verify
├── backend/          # Python / FastAPI + SQLAlchemy 2 / Alembic + asyncio worker (uv)
│   ├── app/          #   api (routers) · services (domain) · models · chain (web3 client)
│   └── worker/       #   watcher · withdrawer · main (per-chain asyncio loops)
├── frontend/         # Next.js + Tailwind (TS); typed client codegen'd from OpenAPI
├── packages/shared/  # chain/token/NFT registry — one source of truth, TS + Python consumers
├── infra/            # docker-compose + e2e.sh
└── docs/             # architecture / api / db / types coordination docs
```

---

## 🛡️ Security notes (what production would change)

This demo holds keys in an env‑var mnemonic with a single hot wallet. Production would use **KMS/HSM‑held
keys** encrypted at rest, **withdrawal approval workflows + limits**, **cold‑storage sweeps**, tuned reorg
depth, rate limiting, and 2FA. These are documented as stretch items — not silently dropped.

---

## 🧰 Tech stack

**Backend** Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic · web3.py · Pydantic v2 · Postgres 16 · uv  
**Contracts** Solidity 0.8.28 · Hardhat · OpenZeppelin · ethers  
**Frontend** Next.js 15 · TypeScript · Tailwind · TanStack Query · openapi‑fetch  
**Tooling** pnpm workspaces · Docker Compose · ruff · mypy (strict) · vitest · GitHub Actions CI
