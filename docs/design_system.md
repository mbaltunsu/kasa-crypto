# Design system — Exchange Dark

**Owner: Claude.** The visual source of truth for the frontend. Direction: a real crypto-exchange terminal —
dark, data-forward, trustworthy. Tuned for **eye comfort**: text is softened off pure white and accents are
desaturated so nothing vibrates against the dark canvas, while every pairing still clears WCAG AA.

## Color tokens (v2 — eye-comfort tuned)

| Token | Hex | Role | Contrast on `bg` |
|---|---|---|---|
| `bg` | `#0F172A` | app canvas (midnight slate, not pure black) | — |
| `surface` | `#1B2336` | cards, panels | — |
| `surface2` | `#232B3F` | raised chips, hover, inputs | — |
| `border` | `#2D3A50` | dividers, card edges (softened) | — |
| `ink` | `#DCE3EC` | primary text (softened — avoids white halation) | ~12:1 AAA |
| `ink-hi` | `#F1F5F9` | reserved emphasis (hero balance only) | ~14:1 AAA |
| `muted` | `#94A3B8` | secondary text, labels | ~6:1 AA |
| `gold` | `#F59E0B` | brand / trust / primary CTA | ~7.4:1 |
| `pos` | `#34D399` | positive / up / credited (calm emerald, **not** lime) | ~8.5:1 |
| `neg` | `#F87171` | negative / down / failed (softened red) | ~6.5:1 |
| `tech` | `#A78BFA` | secondary accent (ERC-20 chip, avatars; used sparingly) | ~6:1 |

**Why v2:** the first pass used `#F8FAFC` text (near-pure white → halation/eye strain on dark) and `#22C55E`
(saturated lime-green). v2 softens primary text to `#DCE3EC`, swaps green to a calmer emerald `#34D399`,
gentles red to `#F87171`, and softens borders/violet — reducing total "saturated-accent vibration" while
keeping AA. Brightest white (`ink-hi`) is reserved for the single hero number, not body text.

Semantic mapping (Tailwind): `text-ink` body · `text-muted` secondary · `text-pos`/`text-neg` for
up/down · `bg-gold text-bg` primary buttons · status pills use `bg-{pos|neg|gold}/10 ring-{...}/30`.

## Typography

- **Inter** for all UI text. **JetBrains Mono** for every number, address, and tx hash, always with
  **tabular figures** (`font-variant-numeric: tabular-nums`) so values don't shift between rows.
- Scale: 12 / 14 / 16(base) / 18 / 24 / 32. Body line-height 1.5–1.6. Weights: 400 body, 500 labels,
  600–700 headings/numbers.

## Components & rules

- Radii: `lg` (8px) controls, `xl`/`2xl` (12–16px) cards. Shadows minimal; depth via `surface` layering +
  1px `border`, not heavy drop shadows.
- Icons: **Lucide** (SVG), consistent 1.8–2px stroke. **No emoji.** Icon-only buttons get `aria-label`.
- Color is never the only signal: every status has an icon/label + the color (e.g. amber pill + spinner for
  `broadcast`, green dot + "credited").
- Focus: visible 3px gold focus ring (`:focus-visible`) on all interactive elements.
- Motion: 150–300ms ease transitions; respect `prefers-reduced-motion`; spinners only for in-flight states.
- Numbers: thousands separators; show `available` prominently and `pending` in `gold` as a secondary line;
  only `available` is spendable.
- Responsive: mobile-first; sidebar collapses under `md`; verified at 375 / 768 / 1024 / 1440. `min-h-dvh`.

## Reference

Static mockup: `frontend/mockups/dashboard.html` (self-contained; open in a browser). These tokens map 1:1
into the frontend Tailwind config during the frontend build.
