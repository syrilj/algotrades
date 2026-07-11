# Trade Desk — Brand & Visual Identity

Focused identity for the Next.js web UI that replaces CLI `tools/trade_desk.py`. Audience: founder/trader running live `poc_va_macdha` setups. Goal: calm institutional credibility under dense data—never flashy fintech marketing.

---

## Brand personality

1. **Measured** — decisions paced by structure and gates, not hype  
2. **Precise** — numbers, levels, and labels are exact and scannable  
3. **Quiet** — authority without neon, gradients, or celebration chrome  
4. **Structural** — volume profile, HTF bias, and filters read as hierarchy  
5. **Operational** — feels like a desk tool, not a product landing page  

---

## Name treatment / product naming

| Context | Treatment |
|--------|-----------|
| Product name | **Trade Desk** (two words, title case) |
| Parent system | TradingAlgoWork (rarely shown; footer/settings only) |
| Model line | `poc_va_macdha` in monospace; human label e.g. “POC/VA · MACD-HA” |
| Short mark | **TD** in a square ink mark (see icons) — never “TD$” or rocket glyphs |
| Wordmark | `Trade` in body weight + `Desk` in medium/semibold, same size; no stacked logo in app chrome |
| CLI echo | Keep command names (`analyze`, `watch`, `rank`) as lowercase UI verbs |

**Do not:** TradeDesk (one word) in UI copy, “AI Desk”, “Alpha Terminal”, or taglines like “trade smarter.”

---

## Color system

Surfaces are cool **ink slate** (Bloomberg-adjacent, not crypto black). Accent is **steel teal**—not purple, not cream/terracotta themes, not neon green/magenta.

### Foundations

| Token | Hex | Role |
|-------|-----|------|
| `--td-ink-950` | `#0B1014` | App shell / deepest bg |
| `--td-ink-900` | `#12181F` | Primary canvas |
| `--td-ink-800` | `#1A222C` | Panels, side rails |
| `--td-ink-700` | `#243040` | Elevated cards / sticky headers |
| `--td-ink-600` | `#334155` | Borders, dividers |
| `--td-ink-500` | `#475569` | Muted chrome, disabled |
| `--td-ink-400` | `#64748B` | Secondary text |
| `--td-ink-300` | `#94A3B8` | Tertiary / captions |
| `--td-ink-200` | `#CBD5E1` | Primary text on dark |
| `--td-ink-100` | `#E2E8F0` | Emphasized text / titles |
| `--td-ink-50` | `#F1F5F9` | Rare light surfaces (exports, print) |

| Token | Hex | Role |
|-------|-----|------|
| `--td-brand` | `#2F6F7A` | Brand / focus / primary CTA chrome |
| `--td-brand-muted` | `#1E4A52` | Brand on hover/bg tint |
| `--td-brand-soft` | `#2F6F7A26` | Selected row / focus ring fill (15% α) |
| `--td-accent` | `#8FA3B0` | Quiet metal accent (icons, hairlines) |

Light mode (optional export/print): invert ink scale; keep semantic action hues identical.

### Action semantics (setup labels)

Use **fill chip + solid left rail** on dense boards. Never rely on color alone—pair with label text.

| Action | Token | Hex | Tint bg (`…-soft`) | Meaning |
|--------|-------|-----|--------------------|---------|
| BUY NOW | `--td-action-buy-now` | `#2F6B4F` | `#2F6B4F22` | Classic pullback-in-value — trade now |
| BUY BREAKOUT | `--td-action-buy-breakout` | `#1F7A6B` | `#1F7A6B22` | Level break + volume surge (smaller size) |
| BREAKOUT WATCH | `--td-action-breakout-watch` | `#B0892E` | `#B0892E22` | Near highs; wait for volume expansion |
| PULLBACK ZONE | `--td-action-pullback` | `#3D6E9C` | `#3D6E9C22` | Trend ok — wait for dip into EMA/value |
| AVOID | `--td-action-avoid` | `#A34848` | `#A3484822` | Structure broken / trap / stand aside |
| WAIT | `--td-action-wait` | `#6B7785` | `#6B778522` | Not ready; includes “WAIT (almost ready)” |

Variants:

- `--td-action-avoid-structure` → same as AVOID (suffix in label only)  
- `--td-action-wait-almost` → WAIT color + dashed border  

### Gate pass / fail

| Token | Hex | Soft | Use |
|-------|-----|------|-----|
| `--td-gate-pass` | `#2F6B4F` | `#2F6B4F1A` | Filter/gate satisfied |
| `--td-gate-fail` | `#A34848` | `#A348481A` | Filter/gate failed |
| `--td-gate-neutral` | `#64748B` | `#64748B1A` | Skipped / N/A |

### Chart overlays (POC / VA / VWAP / EMA)

Distinct from action chips so charts stay readable when both appear.

| Overlay | Token | Hex | Line style |
|---------|-------|-----|------------|
| POC | `--td-overlay-poc` | `#C9A227` | 1.5px solid |
| VAL | `--td-overlay-val` | `#3D8B9C` | 1px solid |
| VAH | `--td-overlay-vah` | `#C47B6A` | 1px solid |
| Value area fill | `--td-overlay-va-fill` | `#3D8B9C14` | Band VAL→VAH |
| VWAP | `--td-overlay-vwap` | `#7EB8C9` | 1.5px dashed |
| EMA 22 | `--td-overlay-ema-22` | `#8FAE6E` | 1px solid |
| EMA 200 | `--td-overlay-ema-200` | `#7A8CA8` | 1.5px solid |
| HTF HA bias up | `--td-overlay-htf-up` | `#2F6B4F66` | Background wash / bar tint |
| HTF HA bias down | `--td-overlay-htf-down` | `#A3484866` | Background wash / bar tint |

Candles (subdued): `--td-candle-up` `#3D7A5C` · `--td-candle-down` `#8F4E4E` · wick `--td-candle-wick` `#94A3B8`.

### Functional UI

| Token | Hex | Role |
|-------|-----|------|
| `--td-info` | `#3D6E9C` | Tooltips, docs links |
| `--td-warning` | `#B0892E` | Soft warnings (not AVOID) |
| `--td-focus-ring` | `#2F6F7A` | Keyboard focus (2px) |
| `--td-positive-num` | `#5A9E78` | PnL / expectancy up (text only) |
| `--td-negative-num` | `#C06A6A` | PnL down (text only) |

---

## Typography

| Role | Recommendation | Notes |
|------|----------------|-------|
| Display (sparse) | **Source Serif 4** | Product name / empty-state titles only; never in tables |
| Body / UI | **IBM Plex Sans** | Dense labels, forms, pipeline steps |
| Mono / tabular | **IBM Plex Mono** | Prices, %, Kelly, timestamps; `font-variant-numeric: tabular-nums` |

Fallbacks: `ui-sans-serif, system-ui` / `ui-monospace, Menlo, monospace`.

**Scale (dense app):** Caption 11–12 · Body 13–14 · Label 12 medium · H3 16 · H2 20 · Display 28–32 (rare). Line-height tight on tables (1.25–1.35); body copy 1.45.

**Weights:** Regular 400 body · Medium 500 UI chrome · Semibold 600 headers/actions. Avoid Black/900.

---

## Icon principles

1. **Stroke, not fill** — 1.5px geometric outline; 16 / 20 / 24 sizes  
2. **Optical square** — 2px padding inside viewBox; align to 2px grid  
3. **Quiet metaphors** — levels, gates, watch, profile histogram; no rockets, bulls, lightning  
4. **Monochrome by default** — inherit `--td-ink-300`; semantic tint only on action chips  
5. **TD mark** — rounded-rect (4px) ink-800 fill, “TD” in Plex Sans Medium ink-100; clearspace = 0.25× mark height  
6. **Status dots** — 6–8px circles using action/gate tokens next to text labels  

---

## Do / Don't

**Do**

- Lead with structure: action label → why → levels (POC/VA/VWAP) → size  
- Keep chrome quiet so semantic colors carry hierarchy  
- Use tabular nums for every price and %  
- Show gate pass/fail as small checklist rows, not banners  
- Prefer hairline borders (`ink-600`) over shadows  

**Don't**

- Purple/indigo gradients, neon green/magenta, cream+terracotta “AI landing” looks  
- Confetti, toast fireworks, or “🚀 signal” copy  
- Rainbow charts—overlays stay to the table above  
- Giant hero CTAs or marketing stock photography  
- Color-only encoding without text (a11y + fatigue)  
- Mixing BUY NOW green with candle green as the same token without checking contrast  

---

## Application: Analyze pipeline vs Watch board

### Analyze (single-symbol pipeline)

- **Canvas:** `ink-900`; pipeline as vertical steps on `ink-800`  
- **Emphasis:** gate pass/fail and failed reasons; action chip appears once at the **verdict** step  
- **Chart:** full overlays (POC/VAL/VAH/VWAP/EMAs) with legend using overlay tokens  
- **Typography:** step titles Medium; numeric levels Mono  
- **Motion:** none except subtle step-complete opacity; no celebratory animation on BUY  
- **Voice:** terse—“BUY NOW · pullback to 22 EMA / value”—mirror CLI why strings  

### Watch (multi-symbol board)

- **Canvas:** denser; sticky header `ink-700`; rows `ink-800` / zebra `ink-900`  
- **Emphasis:** action chips left-rail sorted (BUY NOW → BUY BREAKOUT → BREAKOUT WATCH → PULLBACK ZONE → WAIT → AVOID)  
- **Chart:** sparklines or mini last-price only; full overlays deferred to Analyze drill-in  
- **Grouping:** sector headers in ink-400 caps; hot-sector tint optional via `--td-brand-soft`  
- **Refresh:** quiet pulse on `--td-brand` for “last updated”; never flash entire rows  
- **Voice:** board labels match CLI section headers exactly  

Shared: same action hexes in both views so muscle memory transfers from CLI → web.

---

## CSS starter (tokens)

```css
:root {
  --td-ink-950: #0B1014;
  --td-ink-900: #12181F;
  --td-ink-800: #1A222C;
  --td-ink-700: #243040;
  --td-ink-600: #334155;
  --td-ink-400: #64748B;
  --td-ink-300: #94A3B8;
  --td-ink-200: #CBD5E1;
  --td-ink-100: #E2E8F0;

  --td-brand: #2F6F7A;
  --td-brand-muted: #1E4A52;
  --td-brand-soft: #2F6F7A26;
  --td-accent: #8FA3B0;

  --td-action-buy-now: #2F6B4F;
  --td-action-buy-breakout: #1F7A6B;
  --td-action-breakout-watch: #B0892E;
  --td-action-pullback: #3D6E9C;
  --td-action-avoid: #A34848;
  --td-action-wait: #6B7785;

  --td-gate-pass: #2F6B4F;
  --td-gate-fail: #A34848;
  --td-gate-neutral: #64748B;

  --td-overlay-poc: #C9A227;
  --td-overlay-val: #3D8B9C;
  --td-overlay-vah: #C47B6A;
  --td-overlay-va-fill: #3D8B9C14;
  --td-overlay-vwap: #7EB8C9;
  --td-overlay-ema-22: #8FAE6E;
  --td-overlay-ema-200: #7A8CA8;

  --td-font-display: "Source Serif 4", "Iowan Old Style", Georgia, serif;
  --td-font-body: "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif;
  --td-font-mono: "IBM Plex Mono", ui-monospace, Menlo, monospace;
}
```

---

## Quick audit checklist

- [ ] Action chips use table tokens + visible text  
- [ ] Chart legend matches overlay tokens  
- [ ] No purple gradient / neon / cream-terracotta theme  
- [ ] Tabular nums on all prices  
- [ ] Analyze = gates + full chart; Watch = sorted chips + sparse chrome  
- [ ] Contrast ≥ 4.5:1 for body text on ink-900  
