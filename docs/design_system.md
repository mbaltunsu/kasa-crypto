# Kasa design system — "Signal" (v5)

**Owner: Claude.** The committed source of truth for the frontend's visual language. Masters:
`frontend/tailwind.config.ts` (tokens) + `frontend/src/app/globals.css` (canvas, focus, `.num`).
Token **names** are stable across redesigns — only values change, so components never churn when
the palette evolves. The brand-accent slot is still *named* `gold` for class stability; in Signal
it resolves to **electric mint**.

## Concept

A precision instrument for moving value: deep graphite canvas with a faint engineered dot-grid,
hairline borders, soft neutral depth (never colored halos), one electric mint signal color, and
monospace data. DeFi/AI feel — calm surfaces, confident accent, terminal-grade numbers.

## Type

- **Sora** (`--font-inter` slot) — display + UI. Geometric grotesque; weights 400–800. Hero sizes
  via `text-display` / `text-display-sm` (clamp-based, responsive).
- **Spline Sans Mono** (`--font-mono` slot) — all data: balances, amounts, addresses, hashes.
  Always with `.num` (tabular figures).

## Color tokens (v5 — Signal)

| Token | Hex | Role |
|---|---|---|
| `bg` | `#0B0E13` | canvas (with a 2.5%-alpha dot grid etched in `globals.css`) |
| `surface` / `surface2` | `#11151D` / `#181E29` | cards / wells, chips, segmented controls |
| `border` | `#222B39` | hairlines — usually at `/60`–`/80`; full opacity on hover |
| `ink` / `ink-hi` / `muted` | `#DFE6F0` / `#F6F9FD` / `#8C97AB` | text scale |
| `gold` (brand slot) | `#2BC495` | accent: links, active nav, focus, CTAs (`gold-hi` `#57D9AF`, `gold-deep` `#178F6B`) — deliberately dimmed so large CTAs don't fatigue eyes |
| `pos` | `#2BC495` | success/credit — intentionally the brand mint (green = up = brand) |
| `neg` | `#FF5C7A` | errors, debits, destructive |
| `warn` | `#F5B544` | **in-flight/pending** (StatusPill, pending dots, gas LOW) — never the brand color |
| `tech` / `aqua` | `#8B9DFF` / `#5CC8FF` | NFT accents / info |

## Depth & effects

- Elevation: `shadow-card` (resting) → `shadow-pop` (hover/raised) — neutral, low-opacity, large
  blur + a 1px inset top hairline. Legacy `shadow-glow-*` names resolve to quiet neutrals.
- `bg-gradient-gold`: near-flat mint ramp for primary CTAs / the logo tile.
- `bg-gradient-hero`: 5%-alpha mint radial for hero sections — a hint, not an aura.
- Motion: `animate-fade-up` page entrances, `animate-shimmer` skeletons (2.2s), press
  `active:scale-[0.97]`; everything gated by `prefers-reduced-motion`.

## Brand mark

`frontend/src/components/ui/KasaLogo.tsx` — a geometric K carved into a mint squircle with a
signal dot at the K's mouth (value flowing into the vault). Same artwork is the favicon at
`frontend/src/app/icon.svg` (Next App Router auto-serves it). Used in the sidebar/drawer header
and the login hero.

## Network identity

`frontend/src/components/ui/NetworkIcon.tsx` (logos in `frontend/public/networks/`, sourced from
`frontend/assets/`):

- `NetworkIcon chainId` → chain mark (Sepolia→Ethereum, Fuji→Avalanche; unknown chains, e.g. the
  local Hardhat node, get a neutral dot).
- `AssetIcon symbol chainId` → native coins (ETH/AVAX) get the real network mark; tokens get a
  lettered chip **plus a small chain badge** so the network is always visible.

Used on: dashboard balance cards (plus an oversized low-alpha watermark per card), TopBar chain
chips, deposit address rows, history tables, admin gas table, NFT cards, and the login hero.

## Semantics rules

- Mint = brand/identity/success. Amber (`warn`) = anything still moving. Red = terminal-bad.
  Pending must **never** render in the brand color.
- Amounts: `MoneyText` (mono + tabular + optional sign), colored `text-pos`/`text-neg` by direction.
- Focus: 2px mint outline (`globals.css`) — follows each element's own radius.
