# Frontend queries

**Owner: Claude.** How the Next.js frontend consumes the API. Data layer = a typed `openapi-fetch` client
(`frontend/src/api/client.ts`) generated from `packages/shared/openapi.json`, wrapped in TanStack Query for
caching/invalidation. App code imports enums/types only via the barrel `frontend/src/api/enums.ts` (never
the `.gen` file directly).

## Amount-formatting rules (non-negotiable)

- Amounts arrive as **base-unit strings**. Parse with `BigInt(...)`, never `Number(...)`.
- Format for display via `formatAmount(asset, baseUnits)` from `@kasa/shared` (uses the asset's `decimals`).
- Parse user input via `parseAmount(asset, human)` → base-unit `bigint` → `.toString()` on the wire.
- Render numbers in **JetBrains Mono with tabular figures** so values don't shift. Show `available` and
  `pending` distinctly; only `available` is spendable.

## Page → endpoint map

| Page / route | On load (queries) | Actions (mutations) | Invalidates |
|---|---|---|---|
| `/login`, `/register` | — | `POST /auth/login` · `POST /auth/register` | sets tokens → `/me` |
| `/` dashboard | `GET /me` · `GET /wallet/balances` · `GET /transactions?cursor` (recent) · `GET /chains` · `GET /assets` | — | — |
| `/deposit` | `GET /wallet/deposit-addresses` · `GET /assets` | `POST /demo/faucet` (`Idempotency-Key`) | `balances`, `deposits` |
| `/withdraw` | `GET /wallet/balances` · `GET /assets` | `POST /withdrawals` (`Idempotency-Key`) | `balances`, `withdrawals`, `transactions` |
| `/transfer` | `GET /wallet/balances` · `GET /assets` | `POST /transfers` (`Idempotency-Key`) | `balances`, `transactions` |
| `/history` | `GET /transactions?asset_id&cursor` · `GET /deposits?cursor` · per-row `GET /withdrawals/{id}` | — | — |
| `/nfts` | `GET /nfts` | — | — |
| `/admin` (admin only) | `GET /admin/reserves` · `GET /admin/withdrawals?cursor` | `POST /admin/mint-nft` | `reserves`, `nfts` |

## Query keys & caching

- Keys mirror paths + params: `['balances']`, `['transactions', { asset_id, cursor }]`, `['assets', { chain_id }]`.
- `chains` / `assets` are near-static → `staleTime: Infinity` (registry-backed).
- `balances` / `deposits` / `withdrawals` → short `staleTime` + poll while a deposit is `pending` or a
  withdrawal is in a non-terminal status (`requested|approved|signing|broadcast`).
- After any money mutation, invalidate the keys in the table above. Auth tokens via httpOnly cookie or
  in-memory + refresh on `401` (one retry through `POST /auth/refresh`).

## Status → UI

- `DepositStatus`: `seen`/`confirmed` → amber "pending (n/N confs)"; `credited` → green; `orphaned` → red "reverted".
- `WithdrawalStatus`: `requested|approved|signing|broadcast` → amber spinner; `confirmed` → green + explorer
  link; `failed|rejected` → red.
- Every status renders through an exhaustive `switch` over the generated union — a new backend status fails
  the FE typecheck until handled (intended).

## Explorer links

Build via `explorerTxUrl(chainId, hash)` / `explorerAddressUrl(chainId, addr)` from `@kasa/shared` — never
string-concatenate. See [types_and_registry.md](types_and_registry.md).
