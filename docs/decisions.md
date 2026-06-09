# Decisions log

Locked engineering decisions for Kasa, with the review that produced them. Append-only; supersede the
original product spec ([../PLAN.md](../PLAN.md), gitignored) where they conflict.

## Locked architecture decisions

1. **Real double-entry ledger** — `ledger_accounts` + `ledger_transactions` + `ledger_entries`, enforcing
   `SUM(entries.amount) = 0` per asset per transaction. System accounts (hot wallet, deposits-in-transit,
   fees) + per-user accounts. (Not a single signed balance table — exchange engineers would notice.)
2. **Native deposit indexing = direct EOA transfers only.** ERC-20 via `Transfer` logs; native ETH/AVAX by
   scanning block txs to known addresses. Contract-internal value transfers need trace APIs public RPCs
   don't expose → documented out of scope.
3. **Hot-wallet nonce safety** — `hot_wallet_nonces` table + **one serialized withdrawal worker per chain**.
   `SKIP LOCKED` guards DB rows, not nonces.
4. **Sweeper deferred; reserves aggregate correctly** — proof-of-reserves sums hot wallet + every deposit
   address on-chain vs. total ledger liabilities per asset.
5. **RPC resilience** — env-driven provider fallback lists + retry/backoff + chunked log scans; explorer
   URLs fully configurable.
6. **ERC-721 demo path** — admin mints a collectible to a user's deposit address; UI shows owned NFTs +
   explorer link. No NFT custody accounting.
7. **BIP-44 coin type 60** for EVM address reuse across Sepolia/Fuji (documented).
8. **Reorg handling** — on `block_hash` mismatch for a seen/confirmed deposit → mark `orphaned` + reverse
   the ledger credit.
9. **Pending vs available balance** — deposits `seen` but `< N` confirmations show as pending, not spendable;
   `/wallet/balances` returns `available` + `pending`.
10. **Idempotency keys** — `Idempotency-Key` header on `POST /withdrawals`, `/transfers`, `/demo/faucet` →
    mapped to `ledger_transactions.idempotency_key`.
11. **Faucet drain guard** — real testnet tx from a pre-funded key → per-user rate limit + fixed small amount.

## Cross-language types & registry (designed + adversarially reviewed)

See [types_and_registry.md](types_and_registry.md). Key adopted decisions:

- One master per concern; downstream representations generated and CI-gated by `git diff --exit-code`.
- `FastAPI(separate_input_output_schemas=False)` → one schema per model (no `*-Input`/`*-Output` fork).
- `BaseUnit` JSON Schema pinned to `string` in **both** validation and serialization mode; CI forbids any
  base-unit field typed `integer`/`number`.
- Addresses stored **plain EIP-55** (viem 2-arg / EIP-1191 form banned), indexed/compared lowercase.
- Amount math is identical pure-string in TS and Python (no `Decimal` multiply), proven by a shared golden
  vector corpus run by both in CI.
- Registry↔DB parity is a **content hash**, fail-closed at boot (not a row count).
- `deployments.json` stays strictly to its locked fields; `coinType`/derivation live only in the registry.

## Review log

**Codex (gpt-5.5, high effort)** reviewed the original spec → 7 findings (all accepted, became decisions
1–7). Proposed the initial REST contract + DB schema + `deployments.json` shape now seeded in
[api_architecture.md](api_architecture.md) / [db_model.md](db_model.md).

**Claude additions** (became decisions 8–11): reorg reversal, pending/available split, idempotency keys,
faucet drain guard.

**Shared-types + registry design** went through a 4-agent workflow (two research passes → synthesis →
adversarial review). The reviewer caught and we fixed: FastAPI input/output schema split, `WithJsonSchema`
validation-vs-serialization mode, Python `Decimal` precision drift vs TS bigint, viem EIP-1191 checksum
trap, count-based (vs content-hash) parity check, and the `deployments.json` lock-vs-extend tension.

### Parallel custody review of the built backend (Opus + Codex gpt-5.5)

A dual review (Opus multi-agent across 7 dimensions with adversarial verification + Codex gpt-5.5) of the
chain workers, ledger, and money-flow services. **Fixed + tested** in this pass:

- **Idempotency-key isolation (P0)** — a client `Idempotency-Key` was a *global* unique namespace, so
  reusing a faucet/transfer key on a withdrawal made `ledger.post` return the foreign tx **without**
  posting the reservation debit (hot wallet pays out, user never debited), and a key reused across users
  leaked one user's tx to another. Fix: namespace the client key per `(operation, user)` before storing
  (`app/services/idempotency.py`) **and** make `ledger.post` refuse to replay a key under a different
  `(ref_type, ref_id)`.
- **Concurrent-overspend lock (P0)** — withdrawal/transfer did a check-then-debit with no row lock under
  READ COMMITTED. Fix: `ledger.lock_user_asset` takes a `SELECT … FOR UPDATE` on the user's wallet account
  before the balance read (Postgres; no-op on SQLite, which serializes writers).
- **Single-provider receipt check (P0)** — `_tx_known`/`get_receipt` trusted the first provider because
  `TransactionNotFound` was mapped to a normal `None`/`False` return that `_with_failover` never failed
  over. A lost-ack/lagging node made the withdrawer reverse a payout that actually confirmed. Fix:
  `_find_across_providers` polls every provider and only concludes "absent" after all reachable ones agree.
- **Reorg re-converge credit loss (P1)** — deposit credit/reversal idempotency keys embedded `block_hash`,
  so a reorg that re-converged to the original hash collided on the credit key and the re-credit was
  silently swallowed (deposit marked CREDITED with no ledger entry). Fix: per-deposit `credit_revision`
  (migration `0003`) bumped on each resurrection, used in the credit/reversal keys.
- **Withdrawal destination validation (P2)** — `to_address` was any 1..128-char string, normalized only at
  broadcast; the zero/burn address and typo'd EIP-55 checksums were accepted. Fix:
  `app/core/addresses.to_checksum_address_strict` validates shape, rejects the zero address, and enforces
  EIP-55 at request time (`#14`).

A second pass then landed the architectural cluster (all TDD'd):

- **Withdrawal settle depth + reorg guard (P1, #7)** — `confirm_broadcast` now settles/fails a payout only
  once its receipt is buried under `DEPOSIT_CONFIRMATIONS` blocks **and** the block is still canonical; a
  reorged-out or still-fresh receipt stays `BROADCAST` and is re-evaluated, so a payout reorged within the
  window is never permanently settled.
- **Nonce reconcile + rotation reset (P1, #12/#5)** — `_nonce_row` reconciles the persisted counter to
  `max(persisted, chain pending_nonce)` each pass (an out-of-band tx or lost increment can't strand the
  queue), and resets to the new wallet's on-chain nonce when the hot-wallet address changes.
- **Duplicate system accounts (P1, #10)** — `get_or_create_account` selects with `.first()` (never crashes
  on duplicates) and inserts inside a SAVEPOINT with IntegrityError→reselect; migration `0004` adds a
  partial unique index over `system` accounts (`WHERE user_id IS NULL`).
- **Case-insensitive deposit-address uniqueness (P2, #8/#16)** — migration `0005` replaces the
  case-sensitive constraint with a `lower(address)` functional unique index (addresses already stored EIP-55).
- **Reserves liability accuracy (P3, #17)** — `_liabilities` sums each user wallet's *positive* balance
  rather than clamping the grand total, so an anomalous negative account can't mask true liability.
- **block_hash not-found vs outage (P3, #18)** — `block_hash` returns None only for a genuinely not-yet-mined
  block and raises `ChainRpcError` on a total RPC outage (no more silent stall).
- **Reorg finality window (P2, #13)** — the reversal window now reaches `confirmations + max(reorg_depth,
  REORG_FINALITY_DEPTH)` (default 64), keeping a credited deposit reversible for a true finality depth past
  the credit point.

A third pass landed the withdrawer outbox:

- **Signed-tx outbox + first-row nonce race (#3/#9)** — signing is now split from broadcasting across the
  `SenderClient` protocol (`sign_native`/`sign_erc20` → `broadcast_raw`). The withdrawer runs two
  separately-committed phases: `sign_pending` assigns a gap-free nonce, signs, and persists the raw tx +
  nonce + hash (status `SIGNING`, migration `0006` adds `withdrawal_requests.signed_tx`) BEFORE any
  broadcast; `broadcast_signed` then sends the persisted raw tx in nonce order. A crash between the phases
  (or a transient broadcast failure) re-broadcasts the *identical* signed tx at the same nonce — never a
  fresh one — so a payout can't be double-sent or stranded; refunds happen only via the dropped-tx
  reconcile. The first `hot_wallet_nonces` row is created inside a SAVEPOINT with IntegrityError→reselect,
  so a concurrent first-withdrawal pass resolves to the winner's row instead of aborting (#9).

A final pass closed the last gap:

- **Internal-transfer deposits (#11)** — `fetch_internal_transfers` traces blocks via
  `debug_traceBlockByNumber` (callTracer) and credits native value delivered to a deposit address
  through a contract internal call, each with a distinct, stable negative `log_index` so it dedups
  independently of the top-level send. It is **opt-in** (`WATCH_INTERNAL_TRANSFERS`, default off) and
  gracefully no-ops when no provider exposes the trace namespace, so the normal scan is never slowed
  or broken — enable it only against a trace-capable RPC (Alchemy/QuickNode-class). The trace parsing
  is a pure, fully-unit-tested function (`internal_transfers_from_trace`).

All 18 review findings are now addressed (17 fixed + tested; #11 shipped as an opt-in capability).

## NFT support + custody (supersedes decisions 4 & 6)

The ERC-721 path graduated from "admin mints a collectible, UI shows it, no custody accounting"
(old decision 6) to a full custody model, and the deposited-asset **sweeper** that decision 4
deferred is now **implemented for NFTs**:

- **NFT custody model.** NFTs bypass the double-entry ledger (`nft_holdings` is the source of truth,
  statuses `held|withdrawing|withdrawn`); fungible value stays on the ledger. Real on-chain ERC-721
  mints go to the **custody hot wallet** (not the user's deposit address) via a nonce-safe two-phase
  outbox (`worker/nft_minter.py`), so the hot wallet can later sign the withdrawal transfer. Internal
  NFT transfers are off-chain `nft_holdings` ownership changes. Withdrawals (`worker/nft_withdrawer.py`)
  sign `safeTransferFrom` from the hot wallet. Deposits are indexed by `worker/nft_watcher.py`.
- **Deposited-NFT sweeper (decision 4, now built for NFTs).** An externally-deposited NFT lands at a
  user's per-user deposit address (owned on-chain by that address), so the hot-wallet withdrawer would
  revert for it. `worker/nft_sweeper.py` consolidates it into custody: `credited deposit → discover →
  fund` (hot wallet sends a fixed gas budget to the deposit address) `→ sweep` (the deposit address's
  HD-derived key signs `safeTransferFrom` into the hot wallet) `→ confirm`. The gas tx serializes on
  the shared `hot_wallet_nonces` row; the sweep tx signs at the deposit address's own nonce. The
  confirm phase reuses the same grace gate as the other outboxes and re-checks `ownerOf == hot wallet`.
  Verified end-to-end on Fuji (external deposit → sweep → hot wallet → user withdrawal settles).

## Live-testnet run — bugs that only a real chain exposed (Sepolia + Fuji)

Running the full stack against live Sepolia + Fuji for the first time (the local Hardhat e2e never
hit these because it uses a single instant RPC) surfaced and fixed three classes of bug:

1. **POA block headers (Avalanche).** Fuji puts >32 bytes in block `extraData`; web3.py's default
   header validation raises `ExtraDataLengthError`, breaking every `get_block`/`block_hash` call — so
   the deposit watcher's confirm/credit pass rolled back and Fuji deposits were seen but never
   credited. Fix: inject `ExtraDataToPOAMiddleware` on every provider (no-op on PoS Sepolia).
2. **"Dropped-tx" false-positive (double-spend).** Every hot-wallet outbox (withdrawer, nft_minter,
   nft_withdrawer, nft_sweeper) reversed a payout/mint as "dropped (nonce superseded)" whenever
   `get_receipt` returned `None` and the nonce had advanced — but a *successfully mined* tx also
   advances the nonce, and a load-balanced RPC (Alchemy) transiently returns a null receipt for a
   fresh tx. Result: confirmed payouts reversed → ledger re-credit / NFT released while gone on-chain.
   Fix: a persistence **grace gate** (`unmined_since_block`, migrations 0012/0013) symmetric with
   settlement — reverse only after the receipt stays absent for `confirmations` blocks; clear the
   marker the moment any receipt appears. The Sepolia mint run captured the exact race live and
   settled correctly.
3. **Dead-chain scan.** The registry carries the dev-only `31337` chain; with no local node a testnet
   run spammed connection errors. Fix: treat a chain with no configured RPC as "not part of this
   deployment" and skip it (worker + admin `/gas`).

## Dual custody review of the NFT branch (Opus multi-agent 7-dimension + Codex gpt-5.5)

A second dual review (Opus workflow: 7 dimensions × adversarial verification by 3 diverse-lens
skeptics, 54 agents; plus an independent Codex gpt-5.5 pass) of the NFT-branch changes. **Fixed +
tested:**

- **Gas-funding credited as a deposit** — the sweeper's hot-wallet→deposit-address gas top-up was
  indexed as a user deposit. Fix: the watcher excludes native transfers whose `from` is the custody
  hot wallet (internal top-ups are never deposits).
- **Dead ownership check** — `nft_sweeper`'s post-sweep `ownerOf == hot wallet` verification called a
  non-existent client method (always `True`). Fix: add `ChainClient.erc721_owner_of` and make the
  check real before marking a sweep SWEPT.
- **Failed sweeps couldn't retry** — the `(chain_id, contract, token_id)` unique index + status-blind
  discovery stranded a FAILED sweep. Fix: discovery re-arms a FAILED sweep to PENDING (bounded by
  `attempts`).
- **Stuck gas-funding** — a `FUNDING` sweep with a lost broadcast never retried. Fix: re-broadcast the
  gas tx at the persisted nonce (idempotent; never allocates a fresh nonce → no gap).
- **Rate limit charged before idempotency** — a same-`Idempotency-Key` retry within the window got a
  429 instead of replaying. Fix: idempotency lookup runs before `enforce_rate_limit` (withdrawal,
  NFT withdrawal, faucet).

**Reviewed and consciously kept (documented, not "fixed"):**

- **`FOR UPDATE` (no `SKIP LOCKED`) on `hot_wallet_nonces`** is *intentional* serialization of nonce
  allocation; `SKIP LOCKED` would hand two outboxes the same nonce. Single row → no deadlock.
- **Two nonce domains in the sweeper** (hot wallet funds gas; the deposit address signs the sweep) is
  correct — they are different signers, ordered by the `FUNDED → SWEEPING` state gate.
- **Terminal states (`CONFIRMED`/`SWEPT`/`WITHDRAWN`) are not re-checked after a deep reorg.** This is
  the codebase's finality model: settle only after `N` confirmations + a canonical block-hash check,
  then treat as final (deposits keep a longer reversal window). Reorg-reversing already-final outbound
  txns is a documented production stretch item, not a demo-scope change.
