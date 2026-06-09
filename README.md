# 🏦 Kasa — Custodial Multi-Chain Exchange Wallet

A runnable miniature of what a crypto exchange does end‑to‑end: every user gets a unique on‑chain
**deposit address**, deposits are **indexed and credited to a double‑entry ledger**, and balances are
spendable via **instant internal transfers** (no gas) or **on‑chain withdrawals** signed from a hot
wallet — across **Ethereum Sepolia** and **Avalanche Fuji**, with **verified** ERC‑20 + ERC‑721
contracts on the explorers.

It also custodies **NFTs (ERC‑721)** the same way: admin‑minted collectibles land in the custody hot
wallet, show in a per‑user gallery, move via instant internal transfers, and withdraw on‑chain — and
an **externally‑deposited NFT** is auto‑**swept** from the user's deposit address into custody (the
hot wallet funds gas, the deposit address signs the transfer) so it becomes withdrawable. The whole
money flow has been **run against live Sepolia + Fuji**, not just a local chain.

![backend](https://img.shields.io/badge/backend-142_tests_passing-brightgreen)
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
| 🟣 Ethereum Sepolia | `DemoToken` (ERC‑20) | `0x7eaD24461F04330365b6064Dd441E7910418Ba97` | [Etherscan ✓](https://sepolia.etherscan.io/address/0x7eaD24461F04330365b6064Dd441E7910418Ba97#code) |
| 🟣 Ethereum Sepolia | `DemoCollectible` (ERC‑721) | `0x8168A39544C6b9bcc49523B6dBbA536C64bC06C3` | [Etherscan ✓](https://sepolia.etherscan.io/address/0x8168A39544C6b9bcc49523B6dBbA536C64bC06C3#code) |
| 🔺 Avalanche Fuji | `DemoToken` (ERC‑20) | `0x7B39AF42c4E4cd39F13869B35C9b4a96ED1AeF26` | [Snowtrace ✓](https://testnet.snowtrace.io/address/0x7B39AF42c4E4cd39F13869B35C9b4a96ED1AeF26#code) |
| 🔺 Avalanche Fuji | `DemoCollectible` (ERC‑721) | `0xc6F0820431c42e0411120c156660222fD09Fb134` | [Snowtrace ✓](https://testnet.snowtrace.io/address/0xc6F0820431c42e0411120c156660222fD09Fb134#code) |

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

1. **API** (FastAPI, stateless) — auth, balances, deposit addresses, withdrawals, transfers, admin, faucet, NFTs.
2. **Watcher / indexer** — per‑chain scan from `last_scanned_block` for ERC‑20 + ERC‑721 `Transfer` logs +
   native deposits → **idempotent** `onchain_deposits` / `nft_deposits` → credits the ledger (or records the
   NFT holding) after _N_ confirmations, **re‑validating the block hash** and reversing on reorg.
3. **Custody outboxes** — `SKIP LOCKED` queues, **one serialized worker per chain**, a persisted
   hot‑wallet nonce table, two‑phase **sign → broadcast → confirm**, reversing on failure. Four share the
   hot wallet: fungible **withdrawals**, NFT **mints**, NFT **withdrawals**, and the NFT deposit **sweeper**
   (which funds a user's deposit address for gas, then has that address sign the token into custody).

A single BIP‑39 master mnemonic derives a hot wallet (`m/44'/60'/0'/0/0`) and a unique deposit address per
user (`m/44'/60'/0'/0/{hd_index}`) — the **same address across EVM chains**, as is realistic. NFTs bypass
the ledger (`nft_holdings` is their source of truth); fungible value stays double‑entry.

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

The **NFT** lifecycle mirrors it and was verified on live Fuji + Sepolia:

```
admin mint ─► minted into the custody hot wallet (ownerOf == hot wallet)
internal transfer ─► off‑chain nft_holdings owner change (no gas, no chain tx)
withdraw ─► hot wallet safeTransferFrom ─► ownerOf == external
─── and for an externally‑deposited NFT ───
deposit to user's address ─► watcher credits (held) ─► sweeper funds gas + sweeps
                          ─► ownerOf == hot wallet ─► now withdrawable
```

### 🛡️ Correctness & safety properties (enforced + tested)

- **Double‑entry ledger** — every transaction posts entries that **sum to zero per asset** and is
  **idempotent** on an idempotency key; balances are *summed*, never a mutable column.
- **Reorg‑safe deposits** — credit only after _N_ confs *and* a block‑hash re‑check; a reorg orphans the
  deposit, **reverses the credit**, rewinds the cursor, and re‑credits the re‑mined tx.
- **Custody‑safe outboxes** — every hot‑wallet sender (withdrawals, NFT mints, NFT withdrawals, the NFT
  sweeper) signs → persists → broadcasts → confirms, with gap‑free nonces. A successfully‑mined tx is
  **never falsely reversed** as “dropped”: a receipt that lags on a load‑balanced RPC is held under a
  **grace gate** (reverse only after the receipt stays absent for _N_ blocks), settled the moment it
  appears. Settlement waits _N_ confirmations **and** a canonical block‑hash re‑check.
- **NFT custody** — minted/swept NFTs are held by the hot wallet so withdrawals settle; a deposited NFT
  is swept from the user’s deposit address into custody (per‑address HD key signs, hot wallet funds gas)
  and verified by an on‑chain `ownerOf` re‑check before it’s marked swept.
- **Amounts** — integer base units, **string on the wire, never float**; the identical pure‑string
  algorithm in TS and Python is proven by a shared golden‑vector corpus.
- **Addresses** — stored EIP‑55 checksummed, compared lowercase.

These weren’t free. An adversarial multi‑agent review hardened **18 findings** in the original worker,
and **running the stack on live Sepolia + Fuji** (not just the local chain) exposed three more classes
that a single instant RPC hides: missing **POA middleware** (Avalanche block reads failed, so Fuji
deposits never credited), the **dropped‑tx false‑positive** above (a load‑balanced RPC’s lagging receipt
reversed confirmed payouts), and a gas‑funding transfer being mis‑credited as a deposit. A second
dual review (multi‑agent + an independent model) over the NFT branch fixed five more. The remaining
edge — re‑checking an *already‑final* tx after a deep reorg — is left as a documented finality
assumption ([decisions log](docs/decisions.md)).

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
| Backend (pytest, mocked‑web3, no network) | **142 passing** |
| Shared registry (vitest, incl. cross‑language parity) | **37 passing** |
| Contracts (Hardhat) | **6 passing** |
| Types | **mypy `--strict` clean** across 111 files |
| End‑to‑end (`make e2e`, real local chain) | **green** |
| Contracts on Sepolia + Fuji | **deployed & verified** |
| Live testnet flow (Sepolia + Fuji) | **run on‑chain**: fungible + NFT mint/transfer/withdraw, deposit→credit, NFT deposit→sweep→withdraw, rate‑limit `429` |

---

## 📁 Repository layout

```
kasa/
├── contracts/        # Hardhat + Solidity (ERC-20 + ERC-721) + TS deploy/verify
├── backend/          # Python / FastAPI + SQLAlchemy 2 / Alembic + asyncio worker (uv)
│   ├── app/          #   api (routers) · services (domain) · models · chain (web3 client)
│   └── worker/       #   watcher · withdrawer · nft_watcher/minter/withdrawer/sweeper · main (loops)
├── frontend/         # Next.js + Tailwind (TS); typed client codegen'd from OpenAPI
├── packages/shared/  # chain/token/NFT registry — one source of truth, TS + Python consumers
├── infra/            # docker-compose + e2e.sh + dev/ (local-chain & testnet stack scripts)
└── docs/             # architecture / api / db / types coordination docs
```

---

## 🛡️ Security notes (what production would change)

This demo holds keys in an env‑var mnemonic with a single hot wallet. Production would use **KMS/HSM‑held
keys** encrypted at rest, **withdrawal approval workflows + limits**, **cold‑storage sweeps**, tuned reorg
depth, rate limiting, and 2FA. These are documented as stretch items — not silently dropped.

---

## 🧰 Tech stack

**Backend** Python 3.13 · FastAPI · SQLAlchemy 2 · Alembic · web3.py · Pydantic v2 · Postgres 16 · uv  
**Contracts** Solidity 0.8.28 · Hardhat · OpenZeppelin · ethers  
**Frontend** Next.js 15 · TypeScript · Tailwind · TanStack Query · openapi‑fetch  
**Tooling** pnpm workspaces · Docker Compose · ruff · mypy (strict) · vitest · GitHub Actions CI
