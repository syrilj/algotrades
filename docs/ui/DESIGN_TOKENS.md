# Trade Desk — Design Tokens

Canonical CSS/token layer for implementation. **Brand intent and hex values live in [`BRAND.md`](./BRAND.md)** — this file extends them with type scale, spacing, icon rules, and gate/action maps for engineers.

Default theme: **dark** (desk). Optional light via `[data-theme="light"]` (map ink scale inverted; keep action/overlay hues).

## Surfaces & brand (from BRAND.md)

```css
:root {
  --td-ink-950: #0B1014;
  --td-ink-900: #12181F;
  --td-ink-800: #1A222C;
  --td-ink-700: #243040;
  --td-ink-600: #334155;
  --td-ink-500: #475569;
  --td-ink-400: #64748B;
  --td-ink-300: #94A3B8;
  --td-ink-200: #CBD5E1;
  --td-ink-100: #E2E8F0;
  --td-ink-50: #F1F5F9;

  --td-brand: #2F6F7A;
  --td-brand-muted: #1E4A52;
  --td-brand-soft: #2F6F7A26;
  --td-accent: #8FA3B0;

  --td-focus-ring: 0 0 0 2px var(--td-ink-900), 0 0 0 4px var(--td-brand);
  --td-radius-sm: 4px;
  --td-radius-md: 6px;
  --td-radius-lg: 8px;
  /* Hairline borders > shadows */
  --td-border: var(--td-ink-600);
  --td-shadow: none;

  --td-ease: cubic-bezier(0.22, 1, 0.36, 1);
  --td-dur-fast: 120ms;
  --td-dur-med: 280ms;
  --td-dur-pipeline: 420ms;
}
```

## Action color map

| CLI `plan.action` | Token | Hex |
|-------------------|-------|-----|
| `BUY NOW` | `--td-action-buy-now` | `#2F6B4F` |
| `BUY BREAKOUT` | `--td-action-buy-breakout` | `#1F7A6B` |
| `BREAKOUT WATCH` | `--td-action-breakout-watch` | `#B0892E` |
| `PULLBACK ZONE` | `--td-action-pullback` | `#3D6E9C` |
| `WAIT` / `WAIT (almost ready)` | `--td-action-wait` | `#6B7785` (+ dashed border if almost) |
| `AVOID` / `AVOID (structure broken)` | `--td-action-avoid` | `#A34848` |

Soft fills: append `22` alpha hex (e.g. `#2F6B4F22`). Always pair color with text label.

## Gate color map

| State | Token | Hex | Lucide |
|-------|-------|-----|--------|
| pass (`ok: true`) | `--td-gate-pass` | `#2F6B4F` | `Check` |
| fail (`ok: false`) | `--td-gate-fail` | `#A34848` | `X` |
| neutral / N/A | `--td-gate-neutral` | `#64748B` | `Minus` |

Pipeline node states: `idle` → `running` (brand border) → `pass` | `fail` | `neutral`.

## Chart overlays

| Level | Token | Hex |
|-------|-------|-----|
| POC | `--td-overlay-poc` | `#C9A227` |
| VAL | `--td-overlay-val` | `#3D8B9C` |
| VAH | `--td-overlay-vah` | `#C47B6A` |
| VA band | `--td-overlay-va-fill` | `#3D8B9C14` |
| VWAP | `--td-overlay-vwap` | `#7EB8C9` |
| EMA22 | `--td-overlay-ema-22` | `#8FAE6E` |
| EMA200 | `--td-overlay-ema-200` | `#7A8CA8` |

## Typography

| Role | Font | Token |
|------|------|-------|
| Display (product / empty only) | Source Serif 4 | `--td-font-display` |
| UI / body | IBM Plex Sans | `--td-font-body` |
| Prices / % / Kelly | IBM Plex Mono + `tabular-nums` | `--td-font-mono` |

**Scale (desktop dense):**

| Name | Size / line | Use |
|------|-------------|-----|
| display | 28–32 / 1.15 | Symbol + action (Analyze hero) |
| h1 | 20 / 1.3 | Page title |
| h2 | 16 / 1.35 | Section |
| body | 13–14 / 1.45 | Copy |
| label | 12 / 1.3 medium | Form labels, gate keys |
| caption | 11–12 / 1.25 | Timestamps, hints |
| mono-price | 13–14 mono | All money/% |

## Spacing (4px)

`4 · 8 · 12 · 16 · 24 · 32 · 48` → `--td-space-1` … `--td-space-8`. Desk rows ~32–36px tall.

## Icon rules

- **lucide-react**, stroke `1.75`, sizes 14 / 16 / 20
- No emoji, no glow fills, no rounded-full icon pills
- Sector chips: `--td-radius-sm` squares, not capsule pills

### Pipeline icons

| Stage | Icon |
|-------|------|
| OHLCV | `CandlestickChart` |
| Volume profile | `Layers` |
| HTF St.MACD-HA | `Activity` |
| Rule candidate | `GitBranch` |
| Filters | `Filter` |
| Risk / Kelly | `Scale` |
| Meta-XGB (v15+) | `BrainCircuit` |
| Action + size | `Target` |

### Sector icons

`mag7→Cpu` · `memory→MemoryStick` · `photonics→Aperture` · `energy→Zap` · `space→Rocket` · `quantum→Atom` · `ai_infra→Server` · `banks→Landmark` · `biotech→Dna` · `metals→Gem` · `consumer→ShoppingBag` · `crypto→Bitcoin` · `beta→LineChart`

## Motion (exactly 3)

1. Pipeline stage activation (`--td-dur-pipeline`)
2. Confidence meter fill once on result
3. Watch row tick opacity flash (`--td-dur-fast`)

## Leaderboard tokens

Quiet metals — not neon trophies. Used by `RankMedal` / `ScoreBar` only.

```css
:root {
  --td-rank-gold: #C9A227;      /* align POC gold family */
  --td-rank-silver: #94A3B8;
  --td-rank-bronze: #A67C52;
  --td-rank-plain: var(--td-ink-400);

  --td-score-track: var(--td-ink-700);
  --td-score-bar: var(--td-brand);
  --td-score-bar-winner: var(--td-brand-muted);

  --td-badge-winner-bg: var(--td-brand-soft);
  --td-badge-winner-fg: var(--td-brand);
  --td-badge-default-border: var(--td-ink-500);
  --td-badge-engine-fg: var(--td-ink-200);
  --td-badge-status-fail: var(--td-action-avoid);
  --td-badge-status-frozen: var(--td-ink-400);
}
```

Winner row: left rail `2px solid var(--td-brand)` + soft fill. No glow.

## Do / don't

See `BRAND.md`. Never: purple-indigo gradients, cream+terracotta, glow spam, multi-layer shadows, emoji.
