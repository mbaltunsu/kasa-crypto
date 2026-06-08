# Architecture

Custodial model: the service holds **one BIP-39 master mnemonic** (`MASTER_MNEMONIC`, env secret in dev;
KMS/HSM in prod) → BIP-32 root. From it:

- a **hot wallet** at `m/44'/60'/0'/0/0` — funded from faucet; pays withdrawals + gas, receives sweeps;
- a **unique deposit address per user** at `m/44'/60'/0'/0/{user.hd_index}` (same address across EVM chains).

## Processes

```
                ┌──────────────┐         ┌──────────────────────────────┐
   browser ───► │  API (FastAPI)│ ──────► │           Postgres           │
                │  stateless    │ ◄────── │  users · assets · ledger_*    │
                └──────────────┘         │  onchain_deposits · withdrawals│
                                          │  chain_cursors · hot_wallet_*  │
   testnet  ┌──────────────────┐         │  (jobs: SELECT … SKIP LOCKED)  │
   RPCs ◄──►│ Watcher / indexer │ ───────►│                              │
            │ (per chain)       │         └──────────────────────────────┘
            └──────────────────┘                    ▲
   testnet  ┌──────────────────────┐                │
   RPCs ◄──►│ Withdrawal processor  │ ───────────────┘
            │ (1 serialized / chain)│
            └──────────────────────┘
```

1. **API** (FastAPI, stateless) — auth, balances, deposit address, withdrawal request, internal transfer,
   history, admin, faucet/simulate-deposit.
2. **Watcher / indexer** (per chain) — scans from `chain_cursors.last_scanned_block` for ERC-20 `Transfer`
   logs + direct native deposits to known addresses → writes `onchain_deposits` (idempotent on
   `chain_id + tx_hash + log_index`) → after N confirmations atomically credits the ledger. On `block_hash`
   mismatch (reorg) → marks `orphaned` and reverses the credit.
3. **Withdrawal processor** — consumes `withdrawal_requests` with `FOR UPDATE SKIP LOCKED`, **one worker per
   chain** (serialized for nonce safety via `hot_wallet_nonces`), checks balance, debits ledger, builds +
   signs + broadcasts from the hot wallet, polls for confirmation, reverses the debit on failure. State machine.
4. *(deferred)* **Sweeper** — moves deposited funds from per-user addresses → hot wallet.

No external broker; only infra dependency is Postgres.

## Key flows

- **Deposit** — UI shows address + QR + a **"Simulate deposit / faucet"** button → API sends a real testnet
  tx from a pre-funded faucet key (rate-limited, fixed amount) to the user's address → watcher sees it →
  pending until N confirmations → ledger credit → balance updates. Recruiter needs no testnet funds.
- **Withdraw** — user submits external address + amount → `withdrawal_requests` row → processor debits ledger,
  signs + broadcasts, confirms; reverses on failure. History links to the explorer.
- **Internal transfer** — sender → receiver email + amount → two ledger entries in one DB transaction
  (debit/credit, Σ = 0), instant, no gas.
- **Admin proof-of-reserves** — total liabilities (Σ ledger by asset) vs on-chain hot-wallet + deposit-address
  reserves; list users + withdrawals. Admin can mint an ERC-721 collectible to a user.

## Confirmations & reorg safety

`onchain_deposits.status`: `seen → confirmed → credited`, plus `orphaned`. A deposit is `seen` immediately,
`confirmed` at `block_number + N ≤ last_finalized_block`, `credited` once the ledger transaction commits.
If a `seen`/`confirmed` deposit's `block_hash` no longer matches the canonical chain, it becomes `orphaned`
and any credit is reversed with a `reversal` ledger transaction. Balances expose `available` (credited,
spendable) vs `pending` (seen/confirmed, not yet spendable).

## Security notes (production gap, stated deliberately)

Dev uses an env-var mnemonic + single hot wallet. Production: KMS/HSM-held keys encrypted at rest,
withdrawal approval workflows + limits, cold-storage sweeps, tuned reorg depth, rate limiting, 2FA.

See [api_architecture.md](api_architecture.md) · [db_model.md](db_model.md) ·
[types_and_registry.md](types_and_registry.md).
