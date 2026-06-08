# Shared types, enums & blockchain registry

The cross-language contract between the TypeScript frontend, the Python backend, and the Solidity contracts.
Designed and adversarially reviewed; the correctness fixes are baked into the sketches below.

**Principle: one master per concern → every other representation is generated and CI-gated by
`git diff --exit-code`.** Two orthogonal seams, same discipline:

- **Registry seam** (chains / tokens / NFTs): master = `packages/shared/data/chains/<chainId>.json`.
  `deploy.ts` writes addresses into it; `deployments.json` (locked shape) + the DB `assets` table are
  **derived projections, never hand-edited**.
- **API-type seam** (request/response shapes + status enums): master = backend Pydantic models / `StrEnum`s
  → `openapi.json` → TS types.

## 1. Data flow

```
data/chains/<id>.json ──gen-schema──► schema/registry.schema.json  (cross-lang JSON-Schema contract)
   │  (deploy.ts writes addresses, plain EIP-55)
   ├──► packages/shared/src/registry.ts        (FE typed lookups)
   ├──► packages/shared/python/kasa_shared/     (BE typed lookups)
   ├──► gen-deployments ──► deployments.json     (LOCKED shape, derived output)
   └──► Alembic seed ──► DB `assets` table       (projection; content-hash parity at boot)

backend Pydantic (StrEnums + BaseUnit) ──export_openapi.py──► packages/shared/openapi.json (committed)
   └────────────── openapi-typescript ──► frontend/src/api/schema.gen.ts ──► openapi-fetch client (committed)
```

Nobody hand-edits the DB `assets` table; nobody hand-edits addresses or `deployments.json`. Humans edit
asset **definitions** in `data/chains/*.json`; tooling derives the rest.

## 2. Enums — single-sourced, never hand-mirrored

- **Data-domain** (`ChainId`, `AssetType`) originate in `packages/shared`; both the TS union and the Python
  type are **generated** from that one definition.
- **Behavior/status** enums originate as backend Pydantic `StrEnum` → flow into `openapi.json` →
  `openapi-typescript` emits TS string-literal unions. App code imports via a stable barrel
  (`frontend/src/api/enums.ts`), never the raw `.gen` file.

| Enum | Values (wire = DB string, lowercase snake_case) | Origin |
|---|---|---|
| `AssetType` | `native`, `erc20`, `erc721` | shared (generated both sides) |
| `ChainId` | `11155111` (ethereum-sepolia), `43113` (avalanche-fuji) | shared registry data (branded number) |
| `UserRole` | `user`, `admin` | backend |
| `DepositStatus` | `seen`, `confirmed`, `credited`, `orphaned` | backend |
| `WithdrawalStatus` | `requested`, `approved`, `signing`, `broadcast`, `confirmed`, `failed`, `rejected` | backend |
| `TransferStatus` | `pending`, `submitted`, `confirmed`, `failed` | backend |
| `LedgerEntryType` | `deposit`, `withdrawal`, `transfer_in`, `transfer_out`, `fee`, `adjustment`, `reversal` | backend |
| `ErrorCode` | `validation_error`, `insufficient_funds`, `unknown_asset`, `unsupported_chain`, `withdrawal_rejected`, `not_found`, `unauthorized`, `rate_limited`, `internal_error` | backend |

`WithdrawalStatus` (custodial approval/signing audit trail) is deliberately distinct from `TransferStatus`
(raw on-chain tx state): a withdrawal *has a* transfer.

```ts
// frontend/src/api/enums.ts — the only place app code imports payload enums
import type { components } from "./schema.gen";
export type DepositStatus    = components["schemas"]["DepositStatus"];
export type WithdrawalStatus = components["schemas"]["WithdrawalStatus"];
export type AssetType        = components["schemas"]["AssetType"];
// CI asserts every name imported here exists in openapi.json.
```

## 3. OpenAPI → TS codegen

Tools: **`openapi-typescript@7.x`** (types only, zero runtime) + **`openapi-fetch@0.17`** (~6 kB typed client).

```jsonc
// frontend/package.json
"scripts": {
  "gen:api":       "openapi-typescript ../packages/shared/openapi.json -o ./src/api/schema.gen.ts",
  "gen:api:check": "openapi-typescript ../packages/shared/openapi.json -o /tmp/s.ts && git diff --no-index ./src/api/schema.gen.ts /tmp/s.ts"
}
```
```python
# backend/scripts/export_openapi.py — deterministic diffs
import json
from pathlib import Path
from app.main import app                      # all side effects in lifespan, not import time
out = Path(__file__).resolve().parents[2] / "packages" / "shared" / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
```
```ts
// frontend/src/api/client.ts (hand-written once)
import createClient from "openapi-fetch";
import type { paths } from "./schema.gen";
export const api = createClient<paths>({ baseUrl: process.env.NEXT_PUBLIC_API_URL });
```

**Decisions forced by review (must hold):**

- **`FastAPI(separate_input_output_schemas=False)`** → one schema per model. Otherwise FastAPI emits
  `Foo-Input` *and* `Foo-Output`, silently forking FE/BE types. CI asserts each schema name the FE barrel
  imports actually exists in `openapi.json`.
- **`BaseUnit` advertises `string` in BOTH validation and serialization JSON Schema.** A grep over
  `openapi.json` forbids any base-unit field typed `integer`/`number` — that is the check that prevents a
  balance being typed `number` on one side and `BigInt()`-parsed on the other (2⁵³ corruption).
- **Error envelope:** one `ErrorResponse { code: ErrorCode, message, details[], request_id? }` registered on
  `400/401/404/409/422/429` **and** a `default`/`500` mapping, backed by global handlers for
  `RequestValidationError` / `HTTPException` / `Exception`. Includes `internal_error` so the FE
  `switch (error.code)` is exhaustive with a real default branch.
- **Commit both** `openapi.json` and `schema.gen.ts`; freshness is CI-gated (`git diff --exit-code`).
- snake_case end-to-end (no `by_alias` camelCase) so the codegen never tracks two naming conventions.

```python
# backend/app/types/amount.py — wire branding (ties §3 codegen to §7 amounts)
from typing import Annotated
from pydantic import BeforeValidator, PlainSerializer, WithJsonSchema, AfterValidator

_PAT = r"^-?(0|[1-9]\d*)$"
BaseUnit = Annotated[
    int,
    BeforeValidator(_to_int),                                   # str|int -> int; rejects bool/leading-zeros/floats
    PlainSerializer(lambda v: str(v), return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "pattern": _PAT}, mode="validation"),
    WithJsonSchema({"type": "string", "pattern": _PAT}, mode="serialization"),  # BOTH modes — review fix
]
UnsignedBaseUnit = Annotated[BaseUnit, AfterValidator(_nonneg)]  # balances >= 0; signed BaseUnit for ledger deltas
```

## 4. Registry file layout (`packages/shared`)

```
packages/shared/
  package.json                 # "@kasa/shared"
  src/
    index.ts                   # public barrel
    consts.ts                  # AssetType const-object; EVM_COIN_TYPE=60 — the ONLY place literals live
    schema.ts                  # Zod: Chain, Asset (discriminated union), RegistryManifest — shape source
    types.ts                   # z.infer<> exports: Chain, Asset, Native/Erc20/Erc721Asset, ChainId, Address
    registry.ts                # buildRegistry(): load JSON → Zod validate → frozen indices (singleton)
    api.ts                     # typed lookup free-functions (§6)
    amounts.ts                 # base-unit parse/format — bigint only, never Number()
    address.ts                 # toChecksum() plain EIP-55, toLookupKey() lowercase, isAddressEqual()
  data/
    registry.json              # manifest { version, updatedAt, chainIds: [11155111, 43113] }
    chains/11155111.json       # Ethereum Sepolia: chain meta + assets[]
    chains/43113.json          # Avalanche Fuji
  schema/registry.schema.json  # EMITTED from Zod — the cross-language contract
  scripts/{gen-schema,gen-deployments,check-parity}.{ts,py}
  openapi.json                 # API contract (Codex writes, Claude reads)
  deployments.json             # LOCKED shape, DERIVED via gen-deployments (output, not input)
  python/kasa_shared/          # consts.py · models.py (Pydantic mirror) · registry.py · amounts.py
```

Per-chain data files (not one blob) so `deploy.ts` writes are scoped to a single chain → no merge conflicts,
and "add a chain = add a file" is literally true. `registry.json` is a thin manifest of which files to load.

## 5. Keying rules (enforced at load, fail-fast)

- **`chainId: number` is the sole canonical key** (`Map<ChainId, …>` / `dict[int, …]`). Names/slugs never key.
- **Addresses stored plain EIP-55** (`getAddress(addr)` — **the 2-arg `getAddress(addr, chainId)` / EIP-1191
  form is lint-banned**, it produces checksums incompatible with `eth_utils.to_checksum_address`) but
  **indexed and compared lowercase** via `toLookupKey()`. Every cross-store comparison (registry↔DB, parity,
  address→asset) goes through lowercase.
- **Symbols indexed UPPERCASE** (case-insensitive); display uses stored casing.
- **Native assets have no address** at the type level (`address?: never`).
- **Collision detection at load** (chainId, symbol-per-chain, address-per-chain) → throws at boot.
- A TS↔Py vector asserts `getAddress` and `to_checksum_address` produce identical output for a fixed sample.

## 6. Typed lookup API (mirrored TS ↔ Python)

```
TypeScript (api.ts)                         │  Python (registry.py, frozen singleton)
────────────────────────────────────────────┼──────────────────────────────────────────────
getChain(id): Chain            // throws     │  get_chain(chain_id) -> Chain                # raises
listChains(): Chain[]                         │  list_chains() -> list[Chain]
tokensOfChain(id): Asset[]                    │  tokens_of_chain(chain_id) -> list[Asset]
erc20sOfChain(id) / nftsOfChain(id)           │  erc20s_of_chain / nfts_of_chain
assetBySymbol(id, sym): Asset | undefined     │  asset_by_symbol(chain_id, sym) -> Asset | None
assetByAddress(id, addr): Asset | undefined   │  asset_by_address(chain_id, addr) -> Asset | None
getAsset(id, key): Asset       // throws      │  get_asset(chain_id, key) -> Asset           # raises
nativeAsset(id): NativeAsset                  │  native_asset(chain_id) -> NativeAsset
isNative/isErc20/isErc721(a): a is …          │  a.type == AssetType.NATIVE / ERC20 / ERC721
decimalsOf(a): number                         │  decimals_of(a) -> int
explorerTxUrl(id, hash) / explorerAddressUrl  │  explorer_tx_url / explorer_address_url
derivationPath(id, hdIndex): string           │  derivation_path(chain_id, hd_index) -> str
formatAmount(a, baseUnits) / parseAmount(a, h)│  format_amount / parse_amount
```

- `getAsset` dispatches on a **strict** `^0x[0-9a-fA-F]{40}$` test (not a loose `0x` guess); the native
  sentinel `0xEeee…EEeE` maps to the native asset; symbols are asserted never 0x-prefixed at load.
- URL builders are template-driven (`explorerTxUrl` fills `{hash}`; `explorerAddressUrl` checksums then
  fills `{address}`) — no string concat at call sites.
- `derivationPath` construction lives in a backend-only subpath; nothing key-shaped ships to the browser.

## 7. Amounts — integer base units, string on the wire, never float

`2²⁵⁶` overflows `2⁵³`, so any path through a JS `number` or a JSON number literal corrupts balances. TS and
Python implement the **identical** pure-string algorithm — **no `Decimal` multiply** (its 28-sig-fig context
silently rounds high-precision amounts).

```ts
// amounts.ts
export function parseAmount(asset: Asset, human: string): bigint {
  const d = decimalsOf(asset);
  const neg = human.trim().startsWith("-");
  const [w, f = ""] = human.trim().replace(/^-/, "").split(".");
  if (f.length > d) throw new RangeError(`too many decimals for ${asset.symbol} (max ${d})`);
  const v = BigInt((w || "0") + f.padEnd(d, "0"));   // never touches floating point
  return neg ? -v : v;
}
```
```python
# amounts.py — mirrors the TS string algorithm exactly (no Decimal multiply)
def parse_amount(asset, human: str) -> int:
    d = decimals_of(asset)
    s = human.strip(); neg = s.startswith("-"); s = s.lstrip("-")
    whole, _, frac = s.partition(".")
    if len(frac) > d:
        raise ValueError(f"too many decimals for {asset.symbol} (max {d})")
    v = int((whole or "0") + frac.ljust(d, "0"))
    return -v if neg else v
```

A **shared golden-vector corpus** (positive + negative fixtures) is run by both TS and Python in CI — so
"mirrored" is proven, not asserted. `erc721.decimals` is pinned to literal `0` in both Zod and Pydantic so
`formatAmount` can't be misused on an NFT. DB columns are `numeric(78,0)`; signed-delta ledger columns have
no `>= 0` check, balance columns do.

## 8. No-drift guarantees (all CI-enforced)

1. `export_openapi.py` then `git diff --exit-code packages/shared/openapi.json`; `gen:api` then
   `git diff --exit-code frontend/src/api/schema.gen.ts`.
2. `check-parity`: `ChainId`/`AssetType` identical both sides; every `data/*.json` validates against the
   emitted `registry.schema.json`, **including negative fixtures both validators must reject**.
3. **Content-hash registry↔DB parity at boot:** hash sorted `(chain_id, type, lower(address), symbol,
   decimals)` over registry vs DB rows; **fail-closed** (a count check would miss a wrong decimals value).
4. `gen-deployments` validates its output against the **locked** `deployments.json` schema and refuses to
   emit registry-only fields — `coinType`/derivation stay in the registry, never in `deployments.json`.

## 9. Adding a chain / token / NFT (honest edit count)

| Scenario | Edits | Code changes? |
|---|---|---|
| **New chain** (e.g. Base Sepolia 84532) | +1 line in `data/registry.json` · +1 new `data/chains/84532.json` (meta + assets, `rpcEnv:"RPC_BASE_SEPOLIA"`, `coinType:60`) · provision the `RPC_BASE_SEPOLIA` env var · then deploy + seed | none in lookups/logic |
| **New ERC-20** | append 1 object to that chain's `assets[]` · deploy fills `address`/`deploymentBlock` · re-seed | none |
| **New ERC-721** | append 1 object (`decimals` fixed to `0` by schema) · deploy · re-seed | none |

`ChainId` is a branded number derived from the data, so there is **no enum file to touch**; the one real
out-of-repo step for a new chain is provisioning its RPC env var.

## 10. Ownership

| Path | Owner |
|---|---|
| `contracts/**`, `contracts/scripts/deploy.ts` | Claude |
| `packages/shared/src/**`, `data/**`, `schema/**`, `scripts/gen-*.ts`, generated `deployments.json` | Claude |
| `frontend/src/api/{client,enums,schema.gen}.ts` | Claude |
| `packages/shared/python/kasa_shared/**` | Codex |
| `backend/app/**` (Pydantic, StrEnums, `types/amount.py`, error handlers), `scripts/export_openapi.py`, Alembic seed | Codex |
| `packages/shared/openapi.json` | Codex writes · Claude reads |
| `scripts/check-parity.{ts,py}` + golden-vector corpus | Co-owned (TS: Claude, Py: Codex) |

**Sources:** [openapi-typescript](https://openapi-ts.dev/) · [FastAPI separate input/output schemas](https://fastapi.tiangolo.com/how-to/separate-openapi-schemas/) · [Pydantic JSON Schema modes](https://docs.pydantic.dev/latest/concepts/json_schema/) · [viem getAddress (EIP-1191 warning)](https://viem.sh/docs/utilities/getAddress) · [EIP-55](https://eips.ethereum.org/EIPS/eip-55) · [Uniswap token-lists](https://github.com/Uniswap/token-lists).
