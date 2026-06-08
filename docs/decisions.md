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
