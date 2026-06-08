# Work split & status board

Two agents, ~50/50, two clean seams, no file edited by both.

## Ownership

| Area | Owner | Paths |
|---|---|---|
| Smart contracts | **Claude** | `contracts/**` (ERC-20, ERC-721, Hardhat tests, `deploy.ts`) |
| Shared registry (TS + data) | **Claude** | `packages/shared/{src,data,schema,scripts}/**`, generated `deployments.json` |
| Frontend | **Claude** | `frontend/**` (Next.js, design system, typed client, `schema.gen.ts`) |
| Infra / DX / docs | **Claude** | `infra/**`, `Makefile`, root config, `README.md`, `docs/*` (except the two Codex-owned) |
| Python registry consumer | **Codex** | `packages/shared/python/kasa_shared/**` |
| Backend app | **Codex** | `backend/app/**` (routers, services, Pydantic, `StrEnum`s, `types/amount.py`, error handlers) |
| HD wallet + crypto | **Codex** | `backend/app/core/hd_wallet/**` (+ known-vector tests) |
| Ledger | **Codex** | double-entry implementation + invariants |
| Workers | **Codex** | `backend/worker/**` (watcher, withdrawal processor, nonce mgmt; deferred sweeper) |
| OpenAPI export + DB seed | **Codex** | `backend/scripts/export_openapi.py`, Alembic seed |
| API contract doc | **Codex** | `docs/api_architecture.md` |
| DB model doc | **Codex** | `docs/db_model.md` |
| `check-parity` | **Co-owned** | TS half Claude, Python half Codex |
| Golden-vector amount corpus | **Co-owned** | shared fixtures, run by both |

## The two seams

1. **Contracts → Backend:** Claude publishes `packages/shared/deployments.json` (addresses, decimals,
   `deploymentBlock`) + ABIs → Codex's watcher consumes them.
2. **Backend → Frontend:** Codex publishes `docs/api_architecture.md` + `packages/shared/openapi.json` →
   frontend codegens a typed client. **Any API change goes through `api_architecture.md` first.**

## Delegation mechanics

Codex runs as a write-enabled subagent: `codex exec -m gpt-5.5 -s workspace-write -C backend "<scoped task>"`,
working from `db_model.md` / `api_architecture.md` / `types_and_registry.md`. Claude reviews every Codex
diff (`git diff`) before it lands.

## Status board

| Milestone | Owner | Status |
|---|---|---|
| Repo setup (move spec, gitignore, scaffold) | Claude | ✅ done |
| Coordination docs seeded | Claude | ✅ done |
| Exchange Dark dashboard mockup | Claude | ✅ done (v2 approved) |
| `packages/shared` registry | Claude | ✅ done — 37 tests, tsc strict, generators + parity |
| Contracts (ERC-20/721 + tests + deploy) | Claude | ✅ done — 6 Hardhat tests (Cancun) |
| Backend foundation (enums, amount type, registry consumer, models, alembic, seed) | Codex | ✅ done — 9 tests; content_hash == TS `7b7bc78…` |
| Backend business logic (auth, ledger, API routers, schemas, OpenAPI export) | Codex | ✅ done — 17 tests; 19 endpoints; `openapi.json` emitted |
| Frontend foundation (design system, shell, dashboard, login) + typed client | Claude | ✅ done — `next build` clean; typed client codegen'd, typecheck green |
| Backend workers (watcher + withdrawal processor + nonce mgmt) | Codex | ⬜ next |
| Frontend live wiring + remaining pages (deposit/withdraw/transfer/history/admin) | Claude | ⬜ next |
| Integration (compose + e2e) | Claude | ⬜ |
| Polish / deploy / verify (CI, deploy+verify contracts, README) | Claude | ⬜ |

**Verified cross-language parity:** TS `canonicalRows` and Python `content_hash` both → `7b7bc78ae460fe3317475d32390672cffe218207e12246968ed101c07be8e070`; amount golden vectors pass identically on both sides.

**Verified typed API seam:** backend Pydantic → `packages/shared/openapi.json` (OpenAPI 3.1, 19 paths, no input/output split) → `frontend/src/api/schema.gen.ts` → typed `openapi-fetch` client; base-unit fields typed `string`, status enums as exhaustive unions; frontend `tsc --noEmit` clean.
