# Gamma Exposure Desk — UI Design Spec

**Date:** 2026-07-13  
**Page:** `/gamma`  
**Goal:** A dedicated, symbol-centric gamma-exposure page that fits the existing Trade Desk institutional-terminal language. It is a confirmation layer, not a primary signal. The gamma map is a custom SVG — no chart library, no new dependencies.

## Design system commitments

- **Dense dark UI:** black canvas (`--td-canvas`), near-black panels (`--td-surface-soft`), 1px hairline borders (`--td-hairline`), zero border-radius, no shadows.
- **Steel teal brand:** use `--td-brand` / `--td-brand-muted` for the positive-gamma fills and the expected-move band.
- **Typography:** Source Serif Display for page titles and major headings; IBM Plex Mono for all prices, strikes, GEX values and percentages; IBM Plex Sans for body copy and labels. All numeric values must use `font-variant-numeric: tabular-nums` via `tabular` or `--td-font-mono`.
- **Action colors:** `buy-now` green, `buy-breakout` blue, `breakout-watch` amber, `avoid` red, `wait` muted. Reuse the existing `ActionChip`/`actionStyle` helper.
- **No generic gradients:** no glassmorphism, no cyan-purple chrome, no hero metric cards. Use solid fills and `color-mix` for subtle overlays only.

## 1. Page layout

- **Shell:** render inside the existing `DeskShell` (topbar, brand, nav, `td-main`).
- **Page header:** reuse `PageHeader`.
  - Title: `Gamma`
  - Description: `Dealer gamma exposure by strike. Use as a confirmation overlay for the model verdict.`
  - Meta: symbol in mono (e.g. `APLD`) and `asof_utc` in muted caption.
  - Actions: when a symbol is present, `Analyze`, `Live`, `Options` buttons using `td-btn td-btn-ghost no-underline`.
- **Toolbar:** `td-toolbar` with `td-toolbar__row` containing:
  - Symbol input (`td-field td-field--grow`, `td-input`, uppercase, mono)
  - Spot source select (`td-field`, `td-input`, values: `auto`, `lse`, `yfinance`)
  - Max expiries (`td-field--risk`, small number input)
  - Max DTE (`td-field--risk`, small number input)
  - Run button (`td-btn td-btn-primary td-btn--run`)
- **Main grid:** `grid gap-4 lg:grid-cols-[1.25fr_0.75fr] align-items-start`.
  - **Left column:** `GammaMapPanel` (the custom SVG gamma map) with a panel header and legend.
  - **Right column:** stacked `GammaSummaryCard`, `ModelVerdictComparisonCard`, `GammaNotesCard`.
- **Density:** 1rem gaps, 12–16px panel padding, hairline borders, no rounded corners. Every value is tabular.
- **Empty state:** when no symbol/data, show `td-panel td-ticket--empty` with the title `No gamma exposure` and three numbered steps: enter a symbol, set filters, run.
- **Error state:** `td-alert td-alert--error` with the server message.

## 2. Gamma map visual spec

The map is a single custom SVG inside `GammaMapPanel`. No chart libraries.

### Container

- `td-panel` with the map area full-bleed (no padding around the SVG).
- Panel header (inside the panel, top): `td-eyebrow` `GAMMA BY STRIKE`, a small legend, and the `asof` timestamp in `--td-text-caption`.
- SVG container: `min-height: 360px` with `overflow-x: auto` on the wrapper so a wide strike chain can scroll horizontally.
- SVG: `width="100%"`, `height="100%"`, `preserveAspectRatio="xMidYMid meet"`, computed `viewBox`.

### Axes

- **X-axis:** strike prices along the bottom. Axis line `stroke: var(--td-hairline)`. Tick marks and labels in `--td-font-mono`, `--td-text-caption`, `--td-body`.
- **Y-axis:** net GEX on the left. Labels show signed, scaled values. No grid lines.
- **Zero baseline:** a solid `var(--td-ink)` line at `y=0`, `stroke-width: 1.5`.

### Bars

- One vertical `rect` per strike. `x` centered on the strike, `y` at the top of the bar, `height` proportional to absolute net GEX, `width` scaled to the available strike density.
- **Positive net GEX:** `fill: var(--td-brand)`, `fill-opacity: 0.8`. (Dealer long gamma → pin/mean-revert.)
- **Negative net GEX:** `fill: var(--td-action-avoid)`, `fill-opacity: 0.8`. (Dealer short gamma → amplify/extend.)
- **Hover:** `stroke: var(--td-ink)`, `stroke-width: 1`, `fill-opacity: 1.0`.

### Markers

- **Spot line:** vertical dashed line at `x=spot`, `stroke: var(--td-ink)`, `stroke-width: 2`, `stroke-dasharray: 4 2`. Label at the top: `SPOT {price}` in mono.
- **Expected move shaded band:** vertical rectangle from `expected_move_low` to `expected_move_high` spanning the full chart height. Fill: `var(--td-brand-soft)` with `fill-opacity: 0.25` (no stroke, no gradient).
- **Call wall:** vertical dashed line at `call_wall`, `stroke: var(--td-action-buy-now)`, `stroke-width: 1.5`, `stroke-dasharray: 4 2`. Label: `CALL WALL {strike} (+{dist}%)` in green.
- **Put wall:** vertical dashed line at `put_wall`, `stroke: var(--td-action-avoid)`, `stroke-width: 1.5`, `stroke-dasharray: 4 2`. Label: `PUT WALL {strike} ({dist}%)` in red.
- **Flip strike:** vertical dotted line at `approx_flip_strike`, `stroke: var(--td-action-breakout-watch)`, `stroke-width: 2`, `stroke-dasharray: 2 3`. Label: `FLIP {strike}` in amber.
- **Max pain:** vertical dashed line at `max_pain`, `stroke: var(--td-body)`, `stroke-width: 1`, `stroke-dasharray: 6 3`. Label: `MAX PAIN {strike}` in muted.
- If any value is `null`, hide the marker and label.

### Legend

A horizontal row inside the panel header using small 10px color squares and `--td-text-caption` labels:

- Positive GEX (brand square)
- Negative GEX (red square)
- Spot (white square)
- Expected move (brand-soft square)
- Call wall (green square)
- Put wall (red square)
- Flip (amber square)
- Max pain (muted square)

### Hover tooltips

- Floating HTML tooltip positioned at cursor `x+12, y-12`, `pointer-events: none`, constrained to the panel.
- Content:
  - `STRIKE {strike}` (mono, bold)
  - `Net GEX {net_gex}` (color-coded by sign)
  - `Call {call_gex} · Put {put_gex}` (muted)
  - `Dist {dist}%` from spot
  - Tags (`CALL WALL`, `PUT WALL`, `FLIP`, `MAX PAIN`) rendered as `td-chip` variants when applicable.
- Mobile fallback: each bar carries a `<title>` element with semicolon-delimited values.

## 3. Summary card fields and order

Use `td-panel p-4` with `td-eyebrow` `GAMMA SUMMARY` and a `grid grid-cols-2 sm:grid-cols-3 gap-3` body.

Display in this order, top-to-bottom, left-to-right:

1. **Spot** — `formatUsd(spot)`; second line shows `spot_source` as a `td-chip`.
2. **Net dealer GEX** — `formatNum(net_dealer_gex, 0)` with sign; brand if positive, red if negative, muted if zero.
3. **Regime** — `td-action-chip` mapped from `regime`:
   - `positive_gex_pin` → `PIN` (brand)
   - `negative_gex_amplify` → `AMPLIFY` (avoid red)
   - `flat` → `FLAT` (wait muted)
4. **Call wall** — `{call_wall}` + `({dist_call_wall_pct}%)` in green; if null show `—`.
5. **Put wall** — `{put_wall}` + `({dist_put_wall_pct}%)` in red.
6. **Flip strike** — `{approx_flip_strike}` in amber; if null `—`.
7. **Expected move** — `{expected_move_low} — {expected_move_high}` or `±{expected_move_pct}%` in mono.
8. **Max pain** — `{max_pain}` plus distance from spot in muted.
9. **Near-spot GEX** — `formatNum(near_spot_dealer_gex, 0)` colored by sign.
10. **OTM call volume** — `{otm_call_volume}`.
11. **OTM call OI** — `{otm_call_oi}`.
12. **Expiries used** — `{expiries_used}` truncated or shown as a count.
13. **Asof** — `{asof_utc}` in `--td-text-caption` muted.

## 4. Model-verdict comparison card copy and layout

Card: `td-panel p-4` with `border-left: 3px solid {consensusColor}`.

### Layout

- Header: `td-label` `MODEL VS GAMMA`
- Top row, two columns separated by a `var(--td-hairline)` divider:
  - **Model column:** `td-label` `Model`, an `ActionChip` for the model action (e.g. `BUY NOW`), model name and confidence in mono below.
  - **Gamma column:** `td-label` `Gamma`, an `ActionChip` for the gamma regime (`PIN`, `AMPLIFY`, `FLAT`), plus `Net GEX`, `Call wall`, `Put wall`, `Expected move`, `Flip` in mono.
- Middle row: compact `grid grid-cols-2 sm:grid-cols-4 gap-2` with `Stat` items:
  - `Entry`, `Stop`, `Model risk %`, `Expected move %`
  - If model has size, add `Shares`, `$ risk`, `Account`, `Dist to call wall`.
- Bottom block: a large `td-action-chip td-action-chip--lg` for the consensus verdict, followed by one-sentence operator copy.

### Consensus rules

| Model action | Gamma regime | Consensus chip | Operator note |
|---|---|---|---|
| `BUY NOW` / `BUY BREAKOUT` | `negative_gex_amplify` | `BUY` (model color) | `Gamma is short. Breakouts will accelerate. Follow the model size.` |
| `BUY NOW` / `BUY BREAKOUT` | `positive_gex_pin` | `BREAKOUT WATCH` (amber) | `Gamma is long. Expect chop at the call wall. Wait for a wall break or size down.` |
| `BUY NOW` / `BUY BREAKOUT` | `flat` | `BUY` (model color) | `Gamma is flat. No hedging headwind. Follow the model.` |
| `WAIT` / `BREAKOUT WATCH` / `PULLBACK ZONE` | `negative_gex_amplify` | `BREAKOUT WATCH` (amber) | `Gamma is short. A trigger through the call wall can run fast.` |
| `WAIT` / `BREAKOUT WATCH` / `PULLBACK ZONE` | `positive_gex_pin` | `WAIT` (muted) | `Gamma is long. Range-bound until the flip strikes break.` |
| `AVOID` / `FLATTEN` / `HALT_NEW` | `negative_gex_amplify` | `AVOID` (red) | `Gamma is short. Downside can accelerate. Stand aside.` |
| `AVOID` / `FLATTEN` / `HALT_NEW` | `positive_gex_pin` | `AVOID` (red) | `Gamma is long but model says avoid. No trend edge; wait.` |
| any | `flat` | `WAIT` (muted) | `Gamma is flat. Follow the model trigger.` |

Additional conditional notes, appended when relevant:

- If `entry` is outside `expected_move_low..expected_move_high`: `Entry outside expected move — lower probability.`
- If `entry` is inside: `Entry inside expected move — gamma fits.`
- If `spot` is within `±1%` of `call_wall`: `Price at call wall — resistance risk.`
- If `spot` is within `±1%` of `put_wall`: `Price at put wall — support risk.`
- If no model is available: `No model verdict. Run Analyze first, or use Gamma as a standalone read.` with a link to `Analyze`.

## 5. Notes / interpretation copy for the operator

A `GammaNotesCard` panel (`td-panel p-4`) with `td-eyebrow` `HOW TO READ GAMMA` and the following copy:

- **Net dealer GEX** is the open-interest-weighted dealer gamma position. Positive means dealers are long gamma; they hedge by selling rallies and buying dips, which pins price. Negative means dealers are short gamma; they chase price, which amplifies moves.
- **Call wall** is the strike with the largest absolute call GEX. It often acts as short-term resistance when dealer gamma is positive; a clean break above can accelerate.
- **Put wall** is the strike with the largest absolute put GEX. It often acts as short-term support; a break below can accelerate.
- **Flip strike** is the first strike where cumulative net GEX crosses zero. A sustained close above or below it switches the hedging regime.
- **Expected move** is the one-standard-deviation range implied by the nearest-expiry ATM IV. Treat it as the likely containment zone for the current expiry.
- **Max pain** is the strike where the most option premium expires worthless. It is a short-term magnet only when GEX is also pinning.
- This desk is a confirmation layer. When the model and gamma agree, follow the model. When they conflict, reduce size or stand aside.

## 6. Responsive considerations

- Main grid stacks to a single column below `1024px`.
- Toolbar fields wrap via `td-toolbar__row` and stack on narrow viewports.
- Map panel has `min-height: 320px` and `overflow-x: auto`; the SVG should set a `min-width` of `nStrikes * 12px` so bars remain readable.
- Map legend collapses to a vertical list below `640px` or hides secondary labels (max pain, flip) and shows them only on hover.
- Summary card uses 2 columns on mobile, 3 on `sm` and up.
- Model-verdict card stacks the model/gamma columns vertically below `640px`; the consensus block stays full-width.
- Tooltip uses the SVG `<title>` fallback on touch devices; desktop uses the floating tooltip.
- No page-specific mobile overrides; rely on `td-page` padding and the existing `56px` bottom mobile nav padding.

## 7. CSS class names and tokens to reuse

### Layout / page chrome

- `td-page`, `td-page-header`, `td-page-header__main`, `td-page-header__actions`, `td-page-title`, `td-page-desc`, `td-page-meta`, `td-eyebrow`
- `td-main`, `td-shell`, `td-topbar`

### Panels / forms

- `td-panel`, `td-toolbar`, `td-toolbar__row`, `td-field`, `td-field--grow`, `td-field--risk`, `td-field--account`, `td-field--model`
- `td-input`, `td-label`, `td-btn`, `td-btn-primary`, `td-btn-ghost`, `td-btn--run`
- `td-alert`, `td-alert--error`

### Type / data

- `td-ticker`, `td-ticker-price`, `td-do-next`, `td-muted`
- `tabular`, `font-mono` (for `font-variant-numeric: tabular-nums`)

### Chips / badges

- `td-action-chip`, `td-action-chip--sm`, `td-action-chip--md`, `td-action-chip--lg`
- `td-chip`, `td-chip--warn`

### Disclosure / tables

- `td-details`, `td-details--block`, `td-details__summary`
- `td-row-link`

### Color / font tokens

- Surfaces: `--td-canvas`, `--td-surface-soft`, `--td-surface-card`, `--td-hairline`
- Ink: `--td-ink`, `--td-body`, `--td-body-strong`, `--td-muted`
- Brand: `--td-brand`, `--td-brand-muted`, `--td-brand-soft`
- Actions: `--td-action-buy-now`, `--td-action-buy-breakout`, `--td-action-breakout-watch`, `--td-action-pullback`, `--td-action-avoid`, `--td-action-wait`
- Status: `--td-success`, `--td-warning`, `--td-danger`
- Overlays: `--td-overlay-poc`, `--td-overlay-vwap`, `--td-overlay-vah`, `--td-overlay-va-fill`
- Type: `--td-font-display`, `--td-font-body`, `--td-font-mono`, `--td-text-display`, `--td-text-h1`, `--td-text-h2`, `--td-text-body`, `--td-text-label`, `--td-text-caption`

### React components

- `PageHeader` from `@/components/shell/PageHeader`
- `ActionChip` / `actionStyle` from `@/components/ui/ActionChip`

## Dependencies

None. The gamma map is a custom SVG. The page reuses the existing `GammaResponse` API contract, `PageHeader`, `ActionChip`, and the design tokens above.

## 8. Squeeze read

The backend computes a `squeeze_score` (-100..100) and a `squeeze_label` (`bullish_squeeze`, `bearish_squeeze`, or `neutral`) from:

- Near-spot GEX regime
- Call/put wall proximity
- OTM call/put concentration
- Wall strength asymmetry
- Expected-move position
- Distance to the flip strike

The UI renders the squeeze as a dedicated chip (`BULL SQUEEZE` / `BEAR SQUEEZE` / `NEUTRAL`) and a small signed gauge. When no model signal is available, the consensus defaults to the squeeze read. Squeeze components are returned for transparency and may be surfaced in the notes tooltip.

## 9. Gamma source

The toolbar exposes a **Gamma source** toggle:

- `OI` (default) — yfinance options chain, open-interest weighted.
- `LSE` — `lse-data` options chain, volume/premium weighted.

Both sources produce the same `GammaResponse` shape and run the same squeeze algorithm. The UI uses the `weight` field (`open_interest` / `volume_today` / `premium_today`) to indicate the active source.
