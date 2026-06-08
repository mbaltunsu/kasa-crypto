# API architecture (REST contract)

**Owner: Codex** (backend). Frontend's source of truth. Seeded by Claude; Codex owns ongoing changes — any
change lands here first, then `packages/shared/openapi.json` regenerates and the frontend client follows.

## Conventions

- Base path `//api/v1`. JSON only. `snake_case` everywhere (request, response, DB) — no camelCase aliasing.
- **Amounts are strings in integer base units** (e.g. `"1000000000000000000"` = 1.0 of an 18-decimal asset).
  Never floats, never JSON numbers — see [types_and_registry.md](types_and_registry.md).
- **Auth:** `Authorization: Bearer <access_token>` (JWT, short-lived) + a refresh token. `403` for
  non-admin hitting admin routes.
- **Idempotency:** mutating money endpoints accept an `Idempotency-Key` header → mapped to
  `ledger_transactions.idempotency_key`. Same key replays the same result, never double-spends.
- **Pagination:** opaque `cursor`; responses return `{ items, next_cursor }` (`next_cursor: null` at end).
- **Errors:** uniform envelope, never FastAPI's default `detail` shape:
  ```json
  { "code": "insufficient_funds", "message": "human readable", "details": [], "request_id": "uuid" }
  ```
  `code ∈ ErrorCode` (see types doc) so the frontend does a compiler-checked `switch (error.code)`.
  Global handlers cover `RequestValidationError`/`HTTPException`/`Exception` + a `default`/`500` response.

## Endpoints

| Method | Path | Auth | Request | Response (200/201) |
|---|---|---|---|---|
| POST | `/auth/register` | — | `{ email, password }` | `{ access_token, refresh_token, user }` |
| POST | `/auth/login` | — | `{ email, password }` | `{ access_token, refresh_token, user }` |
| POST | `/auth/refresh` | — | `{ refresh_token }` | `{ access_token }` |
| GET | `/me` | user | — | `{ id, email, role }` |
| GET | `/chains` | — | — | `[{ chain_id, name, symbol, explorer_tx_url }]` |
| GET | `/assets` | — | `?chain_id` | `[{ id, chain_id, symbol, type, contract_address, decimals }]` |
| GET | `/wallet/deposit-addresses` | user | — | `[{ chain_id, address }]` |
| GET | `/wallet/balances` | user | — | `[{ asset_id, chain_id, symbol, available, pending }]` |
| GET | `/deposits` | user | `?cursor` | `{ items: Deposit[], next_cursor }` |
| POST | `/demo/faucet` | user | `{ asset_id, amount }` + `Idempotency-Key` | `{ tx_hash, status }` |
| POST | `/withdrawals` | user | `{ asset_id, to_address, amount }` + `Idempotency-Key` | `{ id, status }` |
| GET | `/withdrawals/{id}` | user | — | `{ id, status, tx_hash, amount, asset_id }` |
| POST | `/transfers` | user | `{ to_email, asset_id, amount }` + `Idempotency-Key` | `{ id, status }` |
| GET | `/transactions` | user | `?asset_id&cursor` | `{ items: LedgerTx[], next_cursor }` |
| GET | `/nfts` | user | — | `[{ chain_id, contract, token_id, explorer_url }]` |
| POST | `/admin/mint-nft` | admin | `{ user_email, chain_id }` | `{ tx_hash, token_id }` |
| GET | `/admin/reserves` | admin | — | `{ assets: [{ asset_id, liabilities, reserves, delta }] }` |
| GET | `/admin/withdrawals` | admin | `?cursor` | `{ items, next_cursor }` |

### Shapes

```
User            { id, email, role: UserRole }
Deposit         { id, chain_id, asset_id, symbol, amount, status: DepositStatus, confirmations, tx_hash, explorer_url, created_at }
Withdrawal      { id, asset_id, chain_id, to_address, amount, status: WithdrawalStatus, tx_hash, explorer_url, created_at }
LedgerTx        { id, type: LedgerEntryType, asset_id, symbol, amount /* signed */, ref, created_at }
Balance         { asset_id, chain_id, symbol, available, pending }   // both base-unit strings
ErrorResponse   { code: ErrorCode, message, details: string[], request_id? }
```

Enum value sets are defined once on the backend and flow to the frontend via OpenAPI — see
[types_and_registry.md](types_and_registry.md). `available` = credited/spendable; `pending` = seen but
under `N` confirmations (not spendable).

## Status semantics

- `DepositStatus`: `seen → confirmed → credited`, or `orphaned` on reorg (credit reversed).
- `WithdrawalStatus`: `requested → approved → signing → broadcast → confirmed`, or `failed`/`rejected`.
- `TransferStatus` (internal): `pending → confirmed` (instant; no chain), or `failed`.

## Open questions for Codex to finalize

- Refresh-token storage/rotation (hashed at rest, single-use rotation) — confirm in `db_model.md`.
- Rate-limit policy values for `/demo/faucet` (per-user/hour, fixed amount per asset).
