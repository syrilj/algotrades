# TradingAlgoWork Production-Readiness + Model Feedback Loop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. On execution start, copy this file to `docs/superpowers/plans/2026-07-13-production-ready-feedback-loop.md` and work from a feature branch (e.g. `prod-ready-v1`), never directly on `main`.

## Context

Three exploration audits (UI, math, feedback-loop) found: (1) a **critical position-sizing bug** — the "Risk %" field sends percent points into a backend fraction parameter, inflating risk 100×; (2) **wrong numbers on the gamma page** — a formatter heuristic turns "+0.8% to call wall" into "+80.0%", and the zero-gamma flip strike picks the near-zero tail instead of the true sign crossing (evidence: APLD flip=10 with spot 31.15); (3) **UI defects** — an invalid-CSS badge tint in OptionsDesk, color collisions in the gamma chart (put wall and negative GEX both identical red; "bullish" rendered blue in one place and green in another), near-invisible separators, stray unicode glyphs where lucide icons are used elsewhere; (4) **no continuous model feedback** — paper-trade outcomes only adjust next-trade sizing; nothing re-ranks models, nothing is scheduled, promotion is fully manual with no queue and no demotion signal.

**User decisions (binding):**
1. **Keep the BMW M theme** (pure black canvas, M blue/red, topbar gradient). Update CLAUDE.md to codify it. Fix only genuine color defects.
2. **Full feedback loop**: blend paper/live outcomes into the leaderboard, scheduled evolve runs, trials.jsonl read-back, promotion queue in the UI.
3. **Manual promotion gate**: the loop nominates; the user approves in the UI. Never auto-overwrite `WINNER.json`.
4. **UI scope**: fix defects + top unifications (action-color module, Chip primitive, EmptyState, formatter consolidation). Do NOT migrate everything off the legacy `--td-ink-*` scale.

**Goal:** Correct all math shown to the trader, fix UI defects while codifying the BMW M design system, and close the model-improvement loop (outcomes → ranking → scheduled evolution → gated promotion).

**Architecture:** Python tools stay the source of truth for all trading math (fractions internally); the Next.js API routes are the unit boundary (UI speaks percent points, routes convert to fractions). The feedback loop reuses existing stores (`runs/paper_ledger/ledger.jsonl`, `models/_shared/trials.jsonl`) and adds one new store (`models/_shared/promotion_queue.json`) plus a scheduler entry point.

**Tech Stack:** Next.js 15 App Router + Tailwind + lucide-react (apps/trade-desk); Python 3 + pandas (tools/); pytest via `.venv/bin/python -m pytest` (tests/ exists; unittest-style tests also run under pytest). No JS test runner exists and none is added — TS verification is `npm run build` + scripted browser checks.

## Global Constraints

- **BMW M palette is law**: pure black canvas (`--td-canvas: #000000`), M blue `#1c69d4` / M red as brand accents, topbar gradient is the ONE sanctioned gradient. Do not introduce teal or revert to the old spec.
- **Action color is law**: each action/verdict maps to exactly ONE hue desk-wide. After this plan: buy-now = green, buy-breakout = azure `#4f8ff0`, breakout-watch = amber, pullback = violet `#5b5fc7`, avoid = red, wait = gray. Bullish = green everywhere in the gamma desk; bearish = red.
- **Risk units convention (exact, project-wide)**: UI form fields and API request JSON carry **percent points** (`riskPct: 0.5` means 0.5%). API routes divide by 100 exactly once when building `--risk-pct` CLI args. All Python (`risk_pct` params, `--risk-pct` flags) is a **fraction** (0.005). `size.risk_pct` in Python JSON responses is a fraction.
- **Percent-display convention**: `formatPct(x)` treats input as a FRACTION (always ×100). `formatPctPoints(x)` treats input as already-percent points (never ×100). Gamma API fields ending `_pct` (`dist_call_wall_pct`, `dist_put_wall_pct`, `dist_flip_pct`, `expected_move_pct`) are percent points (Python already ×100 — do not change the Python side).
- **Never auto-promote**: `WINNER.json` changes only via the approve action a human clicks. The scheduler and evolve loops may only NOMINATE into the promotion queue.
- Python tests: `.venv/bin/python -m pytest tests/ -v`. Frontend check: `cd apps/trade-desk && npm run build` must pass with zero type errors.
- Commit after every task (small, conventional messages). Frontend + Python changes for one logical fix belong in one task/commit.

## File Structure (new files)

- `apps/trade-desk/src/lib/actionColors.ts` — single action/mode/gate/claim → CSS-var mapping
- `apps/trade-desk/src/components/ui/Chip.tsx` — shared bordered-pill primitive (color-mix soft bg)
- `apps/trade-desk/src/components/ui/EmptyState.tsx` — shared empty-state block
- `apps/trade-desk/src/components/ui/Stat.tsx` — shared label/value stat (currently duplicated)
- `apps/trade-desk/src/app/api/promotion/route.ts` — promotion queue GET/POST
- `tools/evolve/promotion_queue.py` — nominate/approve/reject/winner-health
- `tools/evolve_scheduler.py` — nightly loop entry (`--once`, lockfile, log)
- `ops/launchd/com.tradingalgo.evolve.plist` — macOS launchd template
- `tests/test_risk_units.py`, `tests/test_gamma_flip.py`, `tests/test_promotion_queue.py`, `tests/test_rank_live_blend.py`, `tests/test_trials_readback.py`

---

## Phase A — Math correctness (do these first; they affect real risk)

### Task 1: Standardize risk units at the API boundary (CRITICAL, 100× sizing bug)

**Complexity:** standard (multi-file, one concept)

**Files:**
- Modify: `apps/trade-desk/src/app/api/analyze/route.ts` (~line 79–88), `api/picks/route.ts` (~84–92), `api/watch/route.ts` (~122–130), `api/open-scan/route.ts` (~142–150), `api/options-plan/route.ts` (~79–113)
- Modify: `apps/trade-desk/src/components/options/OptionsDesk.tsx:65`
- Modify: `tools/supply_chain.py` (risk_pct default `1.0` → `0.01`, in `_play_for_supplier`/`run_supply_chain` around line 679)
- Test: `tests/test_risk_units.py`

**Interfaces:**
- Consumes: `_position_math(state: dict, account: float, risk_pct: float) -> dict` at `tools/trade_desk.py:899` (risk_pct is a FRACTION — unchanged).
- Produces: every API route converts percent→fraction with `const riskFraction = riskPct / 100;` and passes `args.push("--risk-pct", String(riskFraction))`. Route validation becomes `riskPct > 0 && riskPct <= 5` (5% max per trade) for analyze/picks/watch/open-scan.

**Background for implementer:** `AnalyzeForm.tsx` field is labeled "Risk %", default 0.5, min 0.05 max 5 — user means percent points. `page.tsx:110` sends it verbatim; `trade_desk.py:900` does `risk_budget = account * risk_pct` expecting a fraction. Result: 0.5 → 50% of account risked. `options-plan/route.ts` is the odd one out: it already validates `riskPct <= 1` (fraction) because `OptionsDesk.tsx:65` pre-divides (`risk_pct: riskPct / 100`). Standardize ALL routes to accept percent points.

- [ ] **Step 1: Write the failing test** — `tests/test_risk_units.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import trade_desk  # noqa: E402


def _state():
    return {
        "risk_per_share": 2.0,
        "sleeve_fraction": 1.0,
        "price": 100.0,
        "setup_ok": True,
        "trail_arm": 106.0,
        "symbol": "TESTSYM",
        "model": "test_model",
    }


def test_half_percent_risk_on_10k_is_50_dollars():
    sz = trade_desk._position_math(_state(), account=10_000.0, risk_pct=0.005)
    assert sz["risk_budget"] == 50.0
    assert sz["shares"] == 25            # 50 // 2.0
    assert sz["dollar_risk"] == 50.0
    assert sz["risk_pct"] == 0.005       # fraction, not percent points
```

- [ ] **Step 2: Run it** — `.venv/bin/python -m pytest tests/test_risk_units.py -v`. It should PASS already (backend is correct as a fraction); this test locks the semantics so the boundary fix can't be "solved" by breaking the backend. If `live_adapt.size_mult_for` state on this machine makes sleeve ≠ 1.0 and shares differ, monkeypatch `trade_desk.live_adapt` import or assert only `risk_budget`/`risk_pct`.

- [ ] **Step 3: Fix the four percent-accepting routes.** In `api/analyze/route.ts` replace the validation+push block:

```ts
const riskPct = Number(riskPctRaw);
if (!Number.isFinite(riskPct) || riskPct <= 0 || riskPct > 5) {
  return NextResponse.json(
    { ok: false, command: "analyze", error: "Invalid riskPct (percent points, 0–5]" },
    { status: 400 },
  );
}
// UI speaks percent points; Python --risk-pct is a fraction.
args.push("--risk-pct", String(riskPct / 100));
```

Apply the same pattern in `picks`, `watch`, `open-scan` routes (keep each route's existing `command` string in the error payload).

- [ ] **Step 4: Align options-plan.** In `api/options-plan/route.ts` change validation to percent points (`riskPct > 0 && riskPct <= 100`) and push `String(riskPct / 100)`; in `OptionsDesk.tsx:65` change `risk_pct: riskPct / 100` → `risk_pct: riskPct` (route now owns the conversion). Keep the field label "Max risk %" and default 18.

- [ ] **Step 5: Fix `tools/supply_chain.py`** — the `analyze(symbol, account, risk_pct=1.0)` call chain: change the default to `0.01`.

- [ ] **Step 6: Verify** — `.venv/bin/python -m pytest tests/test_risk_units.py -v` PASS; `cd apps/trade-desk && npm run build` PASS. Grep check: `grep -rn "risk-pct" apps/trade-desk/src/app/api` — every push site must divide by 100 exactly once.

- [ ] **Step 7: Commit** — `fix(risk): UI/API speak percent points, Python speaks fractions — closes 100x sizing bug`

### Task 2: Formatter overhaul — kill the fraction-guessing heuristic

**Complexity:** standard (many call sites, needs judgment per site)

**Files:**
- Modify: `apps/trade-desk/src/lib/format.ts`
- Modify: `apps/trade-desk/src/components/gamma/GammaExposureDesk.tsx` (~lines 214, 222, 229, 595), `components/analyze/VerdictPanel.tsx` (~64, 239), `components/evolve/EvolveDesk.tsx`, `components/watch/WatchBoard.tsx`, `components/picks/PicksList.tsx` (delete local fmtPct/fmtNum/fmtPrice duplicates)

**Interfaces:**
- Produces: `formatPct(value, digits=1)` — input is a FRACTION, always ×100, prefixes `+` for positive. `formatPctPoints(value, digits=1)` — input already percent points, never scaled, prefixes `+`. `formatPctPointsUnsigned(value, digits=1)` — same but no sign prefix (for `±` wrapping). All return `"—"` for null/NaN.

- [ ] **Step 1: Rewrite `format.ts` percent helpers:**

```ts
export function formatPct(value: number | null | undefined, digits = 1): string {
  if (value == null || Number.isNaN(value)) return "—";
  const pct = value * 100; // input is ALWAYS a fraction
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(digits)}%`;
}

/** Input already in percent points (e.g. gamma dist_*_pct fields). */
export function formatPctPoints(value: number | null | undefined, digits = 1): string {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

export function formatPctPointsUnsigned(value: number | null | undefined, digits = 1): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${Math.abs(value).toFixed(digits)}%`;
}
```

Also remove the dead slug from `actionColorClass` (line ~50): return only `` `text-[color:var(${v})]` `` (no CSS rule `td-action-*` exists).

- [ ] **Step 2: Audit EVERY `formatPct` caller** — `grep -rn "formatPct(" apps/trade-desk/src`. For each site decide fraction vs percent-points from the producing Python field. Known conversions: `GammaExposureDesk` `dist_call_wall_pct`/`dist_put_wall_pct` → `formatPctPoints`; `expected_move_pct` inside `±${...}` → `formatPctPointsUnsigned` (fixes the "±+8.5%" double sign); `LiveDesk` `ticket.risk_pct` → stays `formatPct` (fraction). Any caller previously passing values > 1 percent-points into `formatPct` must switch to `formatPctPoints`.

- [ ] **Step 3: Fix VerdictPanel risk display** — lines ~64 and ~239: replace `` `${fmt(size.risk_pct, 2)}%` `` with `formatPct(size.risk_pct, 2)` (fraction 0.005 → "+0.50%"; drop the `+` by using a local unsigned wrap if the design reads odd — acceptable either way, but must show 0.50 not 0.01).

- [ ] **Step 4: Delete duplicate local formatters** — `EvolveDesk.fmtPct/fmtNum`, `WatchBoard.fmtPct/fmtPrice`, `PicksList.fmtPct/fmtPrice`: replace with imports from `@/lib/format`, checking each call's input units against the convention before substituting.

- [ ] **Step 5: Verify** — `npm run build` PASS. Manual: start dev server, open `/gamma?symbol=MU` — wall distances must read like "+0.8%"/"−2.3%" (single sign, sane magnitude), expected move like "±1.2%".

- [ ] **Step 6: Commit** — `fix(format): explicit fraction vs percent-point formatters; remove unit-guessing heuristic`

### Task 3: Gamma flip strike = true sign crossing (+ concentration units, formula label, stale artifacts)

**Complexity:** standard

**Files:**
- Modify: `tools/gamma_exposure.py` (flip at ~382–386 and ~556–560; LSE concentration ~526–534 & ~596–616; header formula comment)
- Modify: `apps/trade-desk/src/components/gamma/GammaExposureDesk.tsx` (~line 443 formula text)
- Delete: `models/poc_va_gex/artifacts/gex_snapshot_*.json` (stale old-schema files with the buggy flip values; the live page never reads them)
- Test: `tests/test_gamma_flip.py`

**Interfaces:**
- Produces: `def _zero_gamma_flip(net_by_strike: pd.Series, spot: float) -> float | None` in `gamma_exposure.py`, used by BOTH the OI-based and LSE-based paths.

- [ ] **Step 1: Write the failing test** — `tests/test_gamma_flip.py`:

```python
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import gamma_exposure  # noqa: E402


def test_flip_is_sign_crossing_near_spot_not_abs_min():
    # cum = [1, 3, -1, 0.5]: crossings at 27.5 (between 20/30) and 36.67 (between 30/40).
    # Old buggy code (cum.abs().idxmin()) returns 40. Correct near spot=31 is 27.5.
    net = pd.Series([1.0, 2.0, -4.0, 1.5], index=[10.0, 20.0, 30.0, 40.0])
    flip = gamma_exposure._zero_gamma_flip(net, spot=31.0)
    assert flip is not None
    assert abs(flip - 27.5) < 1e-9


def test_flip_picks_crossing_nearest_spot():
    net = pd.Series([1.0, 2.0, -4.0, 1.5], index=[10.0, 20.0, 30.0, 40.0])
    flip = gamma_exposure._zero_gamma_flip(net, spot=35.0)
    assert abs(flip - (30.0 + 10.0 * (1.0 / 1.5))) < 1e-9  # ≈36.667


def test_no_crossing_returns_none():
    net = pd.Series([1.0, 1.0, 1.0], index=[10.0, 20.0, 30.0])
    assert gamma_exposure._zero_gamma_flip(net, spot=20.0) is None
```

- [ ] **Step 2: Run** — `.venv/bin/python -m pytest tests/test_gamma_flip.py -v` → FAIL (`_zero_gamma_flip` undefined).

- [ ] **Step 3: Implement** in `gamma_exposure.py`:

```python
def _zero_gamma_flip(net_by_strike, spot: float):
    """Strike where cumulative net GEX crosses zero, nearest to spot (linear interp).

    Replaces cum.abs().idxmin(), which picked the near-zero low-strike tail
    (e.g. APLD flip=10 with spot 31.15).
    """
    cum = net_by_strike.sort_index().cumsum()
    strikes = cum.index.to_numpy(dtype=float)
    vals = cum.to_numpy(dtype=float)
    crossings: list[float] = []
    for i in range(len(vals) - 1):
        a, b = vals[i], vals[i + 1]
        if a == 0.0:
            crossings.append(float(strikes[i]))
        elif a * b < 0:
            crossings.append(float(strikes[i] + (strikes[i + 1] - strikes[i]) * (0.0 - a) / (b - a)))
    if len(vals) and vals[-1] == 0.0:
        crossings.append(float(strikes[-1]))
    if not crossings:
        return None
    return float(min(crossings, key=lambda k: abs(k - spot)))
```

Replace BOTH old blocks (`cum = net_by_strike.cumsum(); ... flip = float(cum.abs().idxmin())`) with `flip = _zero_gamma_flip(net_by_strike, spot)` — keep each site's existing "has both signs" guard semantics (the helper returning `None` covers it).

- [ ] **Step 4: Fix LSE OTM concentration units** (~526–534, ~596–616): when the weight series falls back from volume to premium, the concentration numerators must be computed from the SAME series as `total_weight` (compute `otm_call_weight = weight[otm_call_mask].sum()` etc., instead of always using volume).

- [ ] **Step 5: Fix formula labels** — `GammaExposureDesk.tsx` ~443 and the `gamma_exposure.py` header docstring: displayed formula must match the code’s sign convention (`+Γ` calls / `−Γ` puts): `GEX = Γ · OI · 100 · S² · 0.01, calls +, puts −`.

- [ ] **Step 6: Delete stale artifacts** — `git rm models/poc_va_gex/artifacts/gex_snapshot_*.json` (verify first with `grep -rn "gex_snapshot" apps/ tools/` that nothing reads them; if something does, regenerate instead and note it).

- [ ] **Step 7: Verify** — pytest green; `npm run build`; dev server `/gamma?symbol=MU` shows a flip strike NEAR spot (not at the ladder edge).

- [ ] **Step 8: Commit** — `fix(gamma): flip strike from true sign crossing; concentration unit mix; formula labels; drop stale snapshots`

### Task 4: rr_to_arm — remove the 1.0 floor, use entry basis

**Complexity:** cheap

**Files:**
- Modify: `tools/trade_desk.py` (~lines 932–933 inside `_position_math`)
- Test: extend `tests/test_risk_units.py`

- [ ] **Step 1: Failing test** (append to `tests/test_risk_units.py`):

```python
def test_rr_not_floored_when_arm_below_price():
    st = _state()
    st["trail_arm"] = 99.0  # arm BELOW price → reward must be negative, not floored to rps
    sz = trade_desk._position_math(st, account=10_000.0, risk_pct=0.005)
    assert sz["rr_to_arm"] < 0
```

- [ ] **Step 2: Run** → FAIL (current code floors reward at `rps`, so rr = 1.0).

- [ ] **Step 3: Implement** — replace `reward = max(float(state["trail_arm"]) - px, rps)` with:

```python
basis = float(state.get("entry") or px)
reward = float(state["trail_arm"]) - basis  # no floor: a bad setup shows its true R:R
```

(`state.get("entry")` — check with `grep -n '"entry"' tools/trade_desk.py` whether analyze states carry an entry key; if none exists anywhere, keep `px` as basis and note it in the report.)

- [ ] **Step 4: Run tests** → PASS. Check `VerdictPanel`/anything rendering `rr_to_arm` tolerates negatives (shows e.g. "−0.5" rather than crashing/clamping).

- [ ] **Step 5: Commit** — `fix(sizing): rr_to_arm no longer floored at 1.0; entry-based reward`

---

## Phase B — UI defects + unifications

### Task 5: `actionColors.ts` + shared `Chip` primitive (fixes the broken OptionsDesk badge)

**Complexity:** standard

**Files:**
- Create: `apps/trade-desk/src/lib/actionColors.ts`, `apps/trade-desk/src/components/ui/Chip.tsx`
- Modify: `components/options/OptionsDesk.tsx` (delete local `modeColor` + `ModeBadge`), `components/evolve/EvolveDesk.tsx` (ClaimChip), `components/gamma/GammaExposureDesk.tsx` (RegimeChip/SqueezeChip), `components/ui/ActionChip.tsx` (re-export its mapping through actionColors or consume it)

**Interfaces:**
- Produces: `colorVarFor(kind: "action" | "mode" | "gate" | "claim" | "regime", value: string | null | undefined): string` returning a CSS var reference like `"var(--td-action-buy-now)"`; `<Chip label={...} colorVar={...} title?/>` rendering the bordered pill with `background: color-mix(in srgb, <colorVar> 22%, transparent)`.

**Background:** `OptionsDesk.tsx:26` does ``background: `${c}22` `` where `c = "var(--td-action-buy-now)"` → invalid CSS `var(--td-action-buy-now)22`, tint silently dropped. `ActionChip.tsx` already has the CORRECT `color-mix` pattern — lift it, don't reinvent.

- [ ] **Step 1: Create `actionColors.ts`** consolidating: `format.actionColorVar` (keep re-exported for compat), `OptionsDesk.modeColor` (OPTIONS→buy-now, EQUITY→buy-breakout, FLATTEN/HALT→avoid, else wait), EvolveDesk `claimStyle`, gamma regime/squeeze mappings, LeaderboardTable rank colors, SupplyChainDesk score/conf mappings. One exported function per domain, one file.
- [ ] **Step 2: Create `Chip.tsx`**:

```tsx
export function Chip({ label, colorVar, title }: { label: string; colorVar: string; title?: string }) {
  return (
    <span
      title={title}
      className="inline-flex items-center px-2 py-1 text-[12px] font-semibold tracking-wide"
      style={{
        color: colorVar,
        background: `color-mix(in srgb, ${colorVar} 22%, transparent)`,
        border: `1px solid ${colorVar}`,
        borderRadius: "var(--td-radius-sm)",
      }}
    >
      {label}
    </span>
  );
}
```

- [ ] **Step 3: Replace** `ModeBadge` (OptionsDesk), `ClaimChip` (EvolveDesk), `RegimeChip`/`SqueezeChip` (gamma) with `<Chip>` + `colorVarFor(...)`. Keep visual output identical except the now-working tint.
- [ ] **Step 4: Verify** — `npm run build`; dev server `/options?symbol=APLD`: mode badge now has a visible soft tint.
- [ ] **Step 5: Commit** — `fix(ui): single action-color map + Chip primitive; repairs invalid ${c}22 badge tint`

### Task 6: Gamma chart color scheme — one hue per meaning

**Complexity:** standard (visual judgment)

**Files:**
- Modify: `components/gamma/GammaScene.tsx` (~74, 82, 113–114, 169), `components/gamma/GammaExposureDesk.tsx` (legend ~558–577, SqueezeGauge, SqueezeChip)

**The scheme (exact):**
- Positive net GEX bars: `var(--td-m-blue-dark)` (dealer long gamma / stabilizing)
- Negative net GEX bars: `var(--td-m-red)`
- Call wall line: `var(--td-action-buy-now)` green, dashed `6 3`
- Put wall line: `var(--td-warning)` amber, dashed `6 3` (NO LONGER red — was indistinguishable from negative bars)
- Flip line: `var(--td-body-strong)` dotted `2 3`
- Spot marker: `var(--td-body-strong)` solid
- SqueezeGauge bull zone + bull marker + bullish SqueezeChip: green (`--td-action-buy-now`); bear zone/marker/chip: red (`--td-m-red`). Bullish is green EVERYWHERE in this desk — never brand blue.

- [ ] **Step 1: Apply the scheme** in GammaScene + legend + gauge + chips; update legend labels to match ("Put wall" swatch amber, etc.). Bump the "Expected move" legend swatch to full opacity (it was near-invisible at 0.6 on `brand-soft`).
- [ ] **Step 2: Verify** — dev server `/gamma?symbol=MU`: every legend entry visually distinct; put wall distinguishable from negative bars; screenshot for the review.
- [ ] **Step 3: Commit** — `fix(gamma-ui): distinct wall/bar/flip colors; bullish=green desk-wide`

### Task 7: Token fixes — distinct action blues, visible separators

**Complexity:** cheap

**Files:**
- Modify: `apps/trade-desk/src/app/globals.css` (tokens at ~lines 38–60), `components/evolve/EvolveDesk.tsx` (~101 separator)

- [ ] **Step 1: In `globals.css`:** add `--td-m-violet: #5b5fc7;` next to the other M colors; change `--td-action-pullback: var(--td-m-violet);` and `--td-action-buy-breakout: #4f8ff0;` (lighter azure — now distinct from `--td-brand` #1c69d4 chrome and from pullback). Leave `--td-brand`, `--td-score-bar`, canvas, gradient untouched (BMW M is law).
- [ ] **Step 2: Contrast:** EvolveDesk phase separator `var(--td-ink-600)` (≈1.4:1 on black) → `var(--td-ink-400)`.
- [ ] **Step 3: Verify** — dev server: BUY BREAKOUT chip vs top-bar brand chrome clearly different; PULLBACK vs BUY BREAKOUT clearly different; evolve phase separators visible.
- [ ] **Step 4: Commit** — `fix(tokens): distinct buy-breakout/pullback hues; visible separators`

### Task 8: Icon + misc consistency

**Complexity:** cheap

**Files:**
- Modify: `components/leaderboard/LeaderboardTable.tsx` (~221 `●`/`#`), `components/evolve/EvolveDesk.tsx` (~346 `✓`/`✗`), `components/watch/WatchBoard.tsx` (~105 thead bg, ~91 font fallback), `components/picks/PicksList.tsx` (~119 font fallback), `apps/trade-desk/package.json`

- [ ] **Step 1:** EvolveDesk `✓`/`✗` → lucide `<Check size={12} aria-hidden />` / `<X size={12} aria-hidden />` (match sizing used in analyze panels). LeaderboardTable `●`/`#` rank marker → lucide `<Circle size={8} fill="currentColor" />` / keep `#` as typographic if it reads as "rank number" (implementer judgment; note choice in report). The `.td-details__summary` `▸`/`▾` CSS pseudo-element stays (documented as typographic — CSS can't render lucide without markup churn).
- [ ] **Step 2:** WatchBoard sticky thead: `bg-[var(--td-ink-700)]` → `bg-[var(--td-canvas)]` + bottom hairline border, matching leaderboard/evolve header treatment.
- [ ] **Step 3:** Font fallbacks: `var(--td-font-display,Inter,...)` in PicksList/WatchBoard → `var(--td-font-display,Georgia,serif)`.
- [ ] **Step 4:** lucide-react provenance: run `npm view lucide-react versions --json | tail -5` and `npm view lucide-react@1.24.0 dist.tarball`. If `1.24.0` is a canonical registry release, pin exact (`"lucide-react": "1.24.0"`); if it is NOT canonical, STOP and report BLOCKED with what you found (do not swap libraries unilaterally).
- [ ] **Step 5:** Verify `npm run build`; commit — `fix(ui): lucide icons for glyphs; header/font consistency; pin lucide-react`

### Task 9: Shared `EmptyState` + `Stat` components

**Complexity:** cheap

**Files:**
- Create: `components/ui/EmptyState.tsx`, `components/ui/Stat.tsx`
- Modify: `components/picks/PicksList.tsx` (~113), `components/watch/WatchBoard.tsx` (~85), `components/gamma/GammaExposureDesk.tsx` (~458 + local `Stat` at ~14), `components/options/OptionsDesk.tsx` (~168 + local `Stat` at ~427), `components/evolve/EvolveDesk.tsx` (~533), `components/leaderboard/LeaderboardView.tsx` (~129)

**Interfaces:**
- `<EmptyState icon={LucideIcon} title="..." hint="..." steps?: string[] />` — icon + serif display heading + muted hint; optional numbered how-to list (gamma/options keep their step lists via `steps`).
- `<Stat label="..." value="..." />` — exact markup of the currently duplicated local `Stat` in GammaExposureDesk (lift it verbatim).

- [ ] **Step 1:** Build both components from the existing best-in-class instances (PicksList empty state, GammaExposureDesk Stat). Adopt across all six sites; delete the local duplicates.
- [ ] **Step 2:** Verify each desk's empty state renders (visit each page with no query params) + `npm run build`. Commit — `refactor(ui): shared EmptyState and Stat components`

---

## Phase C — Continuous model feedback loop

### Task 10: Blend paper/live outcomes into `rank_models`

**Complexity:** standard

**Files:**
- Modify: `tools/model_registry.py` (`rank_models` at line 252)
- Test: `tests/test_rank_live_blend.py`

**Interfaces:**
- Consumes: `paper_ledger.compute_stats(symbol=None, model=None) -> dict` (`tools/paper_ledger.py:392`, import-safe) — returns per-(model, symbol) buckets; aggregate per model: `live_n` (closed count), `live_wr`, `live_avg_R`, `live_pnl`.
- Produces: each rank row gains `live_n: int`, `live_wr: float|None`, `live_avg_R: float|None`, `live_pnl: float|None`, `live_status: "none"|"provisional"|"confirming"|"degrading"`, `blended_score: float`. Sort switches to `blended_score`; keep `score` unchanged in the row.

**Blend formula (exact, bounded — no unbounded live influence):**

```python
def _live_factor(live_n: int, live_avg_R: float | None) -> float:
    if live_n < 10 or live_avg_R is None:
        return 1.0  # not enough live evidence to move the rank
    r = max(-0.6, min(0.6, float(live_avg_R)))
    return 1.0 + 0.25 * r  # bounded [0.85, 1.15]
```

`blended_score = round(score * _live_factor(live_n, live_avg_R), 4)`. `live_status`: `"none"` if live_n == 0; `"provisional"` if 0 < live_n < 10; `"confirming"` if live_n >= 10 and live_avg_R > 0; `"degrading"` otherwise.

- [ ] **Step 1: Failing test** — `tests/test_rank_live_blend.py`: unit-test `_live_factor` (n=5 → 1.0; n=10, R=0.4 → 1.10; n=10, R=−2.0 → clamped 0.85) and, monkeypatching `compute_stats` to a fixture, assert a rank row carries the live fields and sorts by `blended_score`.
- [ ] **Step 2: Implement** in `model_registry.py` — wrap the `compute_stats` import in try/except so ranking never breaks when the ledger is absent (all live fields default to none/1.0).
- [ ] **Step 3: Run tests** → PASS. Also run `.venv/bin/python tools/trade_desk.py rank --json | head -40` (or the equivalent invocation the API uses) and confirm rows include the new fields.
- [ ] **Step 4: Commit** — `feat(rank): blend live paper outcomes into model ranking (bounded, min-n gated)`

### Task 11: Leaderboard UI — live columns

**Complexity:** cheap

**Files:**
- Modify: `apps/trade-desk/src/lib/types.ts` (`ModelRankRow`), `components/leaderboard/LeaderboardTable.tsx`, `tools/trade_desk.py` rank handler (~1675: pass new fields through if it reshapes rows)

- [ ] **Step 1:** Extend `ModelRankRow` with `live_n`, `live_wr`, `live_avg_R`, `live_status`, `blended_score` (all optional for back-compat).
- [ ] **Step 2:** Add columns: "Live WR", "Live n", "Avg R" (formatted via `lib/format`; `live_wr` is a fraction → `formatPct`); a small `<Chip>` for `live_status` (`confirming` = buy-now green, `degrading` = avoid red, `provisional` = wait gray via `colorVarFor`). Rows with `live_n < 10` show live cells muted with a "provisional" title attr — honest, not hidden.
- [ ] **Step 3:** Verify — dev server `/leaderboard`: columns render; models without ledger entries show "—". `npm run build`. Commit — `feat(leaderboard): surface live outcomes and status`

### Task 12: Promotion queue backend + winner decay check

**Complexity:** capable (touches promotion safety)

**Files:**
- Create: `tools/evolve/promotion_queue.py`
- Modify: `tools/evolve/finalize.py` (`compare_to_winners` at line 31 — nominate on `candidate_for_manual_promote`)
- Test: `tests/test_promotion_queue.py`

**Interfaces (exact):**

```python
# tools/evolve/promotion_queue.py
QUEUE_PATH = ROOT / "models" / "_shared" / "promotion_queue.json"

def nominate(candidate: dict) -> dict: ...
# appends {"id", "ts", "campaign", "family", "model_dir", "metrics": {...},
#          "gates": {...}, "status": "pending"} — dedupes by id, never touches WINNER

def approve(entry_id: str) -> dict: ...
# 1) mutations.promote_mutation_to_models(entry_as_mut, family=..., version_name=...)
# 2) update models/<family>/WINNER.json: set new winner, move old to previous_winner lineage
# 3) findings.append(kind="promotion", ...)  4) mark entry status="approved"

def reject(entry_id: str, reason: str = "") -> dict: ...

def winner_health(trailing_n: int = 20) -> dict: ...
# compute_stats(model=<current winner id>) over last N closed trades;
# returns {"winner", "live_n", "live_wr", "threshold", "degraded": bool}
# threshold read from models/_shared/PASS_BAR.json (use its win-rate floor; if absent, 0.40)
```

- Consumes: `mutations.promote_mutation_to_models(mut, *, family, version_name)` (`tools/evolve/mutations.py:213` — needs `mut["id"]` and `mut["model_dir"]`), `finalize.load_winner()`, `paper_ledger.compute_stats`.
- HARD RULE: `nominate` and `winner_health` are the ONLY functions the scheduler/evolve loops may call. `approve` is invoked solely by the API route (human click).

- [ ] **Step 1: Failing tests** — with `QUEUE_PATH` monkeypatched to `tmp_path`: nominate→pending entry exists; nominate same id twice → one entry; reject→status recorded; approve with a stubbed `promote_mutation_to_models` (monkeypatch) → stub called once, WINNER-update helper called, status "approved"; `winner_health` with stubbed stats below threshold → `degraded: True`.
- [ ] **Step 2: Implement**; wire `compare_to_winners` to call `nominate(...)` when its decision contains `candidate_for_manual_promote` (import inside the function, try/except so finalize never crashes on queue errors).
- [ ] **Step 3:** pytest green. Commit — `feat(evolve): promotion queue with manual approve; winner decay check`

### Task 13: Promotion API route + UI panel

**Complexity:** standard

**Files:**
- Create: `apps/trade-desk/src/app/api/promotion/route.ts`
- Modify: `components/evolve/EvolveDesk.tsx` (new "Promotion queue" panel), `apps/trade-desk/src/lib/types.ts`

**Interfaces:**
- `GET /api/promotion` → `{ ok, data: { queue: PromotionEntry[], winner_health: {...} } }` (spawns `python tools/evolve/promotion_queue.py --json list` — add a tiny `__main__` CLI to promotion_queue.py with `list|approve <id>|reject <id>` subcommands, following the `runPythonScript` pattern in `src/lib/tradeDesk.ts`).
- `POST /api/promotion` body `{ action: "approve" | "reject", id: string }` → runs the matching CLI subcommand. Validate `id` against `/^[a-zA-Z0-9_\-\.]+$/` before shelling out.

- [ ] **Step 1:** Add the `__main__` CLI to `promotion_queue.py`; build the route on the existing `runPythonScript`/`ApiEnvelope` pattern (copy the shape of `api/evolve/route.ts`).
- [ ] **Step 2:** EvolveDesk panel: pending entries (id, campaign, key metrics via `<Stat>`, gates summary) + Approve/Reject buttons (Approve = green `--td-action-buy-now`, Reject = `--td-action-avoid`; disable while posting; refetch after). Winner-health banner when `degraded: true`: "WINNER degraded — live WR X% over last N trades (floor Y%)" in avoid-red. Empty queue uses `<EmptyState>`.
- [ ] **Step 3:** Verify — dev server `/evolve`: panel renders (empty state OK); with a hand-nominated test entry (`.venv/bin/python tools/evolve/promotion_queue.py nominate-test` — include this dev-only subcommand or seed the JSON manually), Approve round-trips. `npm run build`. Commit — `feat(ui): promotion queue panel with manual approve gate`

### Task 14: trials.jsonl read-back — dedupe + seed next generation

**Complexity:** standard

**Files:**
- Modify: `tools/evolve/loop_core.py` (campaign start + `spawn` path; `write_trial` is ~line 404)
- Test: `tests/test_trials_readback.py`

**Interfaces:**
- Produces in `loop_core.py`: `def load_trial_history(path=TRIALS_PATH) -> tuple[set[str], list[dict]]` returning (`tried_keys`, `top_parents`) where `tried_key = sha1(json.dumps({"parent": t["parent"], "variant_id": t["variant_id"]}, sort_keys=True))` — match whatever uniquely identifies a variant config in existing rows (inspect `models/_shared/trials.jsonl` rows first; if a config/codes dict is present, hash that instead of variant_id, and say so in the report). `top_parents` = top-K (K=5) rows by `fitness` with non-null `lockbox_fitness`.
- Campaign integration: skip spawning a mutation whose tried_key is in history (log the skip count); seed generation-0 parents from `top_parents` when the campaign has no explicit parent.

- [ ] **Step 1: Failing test** — write 3 fake trial lines to a tmp jsonl; assert `load_trial_history` returns 3 keys and parents sorted by fitness desc; assert the spawn filter drops a duplicate spec.
- [ ] **Step 2: Implement**; keep it read-only over trials.jsonl (never rewrite the file).
- [ ] **Step 3:** pytest green; run a smoke `--dry-run`-style invocation if the driver supports one (check `runs/evolve_direction_v1/driver.py phase0` help; do not launch a full campaign). Commit — `feat(evolve): trials.jsonl read-back for dedupe and generation seeding`

### Task 15: Scheduler — nightly bounded loop (macOS launchd)

**Complexity:** standard

**Files:**
- Create: `tools/evolve_scheduler.py`, `ops/launchd/com.tradingalgo.evolve.plist`
- Modify: `AGENTS.md` (document install/run), append scheduler section

**Behavior of `tools/evolve_scheduler.py --once` (also the launchd entry):**
1. Acquire lockfile `runs/scheduler/LOCK` (contains pid; if held by a live pid, exit 0 with a log line — never overlap).
2. Log everything to `runs/scheduler/scheduler.log` (append, timestamped).
3. **Freshness gate:** read `data_cache/MANIFEST.json` mtime; if older than 3 days, run `python tools/snapshot_data.py` (check its actual CLI first: `grep -n "argparse\|add_argument" tools/snapshot_data.py`); if refresh fails, log and ABORT the run (stale-data evolution is worse than none).
4. **Bounded evolve:** `python tools/evolve_pipeline.py rank` with the smallest budget flags the CLI supports (inspect `tools/evolve_pipeline.py` argparse for budget/limit flags and use them; hard timeout 3600s via `subprocess.run(timeout=...)`).
5. **Re-rank:** call `model_registry.rank_models()` (imports fine) and log the top 5 with blended scores.
6. **Nominate:** finalize already nominates via Task 12; additionally call `promotion_queue.winner_health()` and log/flag degradation.
7. Release lock. NEVER call `promotion_queue.approve` — grep-provable: the word `approve` must not appear in this file.

- [ ] **Step 1:** Implement the script exactly as specced (stdlib only: argparse, json, os, subprocess, time, pathlib).
- [ ] **Step 2:** launchd plist template: label `com.tradingalgo.evolve`, `ProgramArguments` = [`<abs .venv python>`, `<abs tools/evolve_scheduler.py>`, `--once`], `StartCalendarInterval` Hour 18 Minute 0, `StandardOutPath`/`StandardErrorPath` → `runs/scheduler/launchd.{out,err}.log`, `WorkingDirectory` = repo root. AGENTS.md gets: `cp ops/launchd/com.tradingalgo.evolve.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.tradingalgo.evolve.plist` + how to run manually (`--once`) and where logs live. Do NOT install the plist yourself — installing a persistent scheduled job is the user's action; the task delivers the file + docs only.
- [ ] **Step 3:** Verify — run `.venv/bin/python tools/evolve_scheduler.py --once` end-to-end once (it may no-op on fresh data — that's a pass; check `runs/scheduler/scheduler.log`). Second concurrent invocation exits cleanly on the lock. Commit — `feat(scheduler): nightly bounded evolve run with freshness gate and lockfile`

---

## Phase D — Docs + final verification

### Task 16: Codify BMW M in CLAUDE.md + document the loop

**Complexity:** cheap

**Files:**
- Modify: `/Users/syriljacob/Desktop/TradingAlgoWork/CLAUDE.md` (Aesthetic Direction + Design Principles), `AGENTS.md`

- [ ] **Step 1:** Rewrite the "Aesthetic Direction" paragraph: BMW M institutional terminal — pure black canvas, M blue (`#1c69d4`) chrome, M tricolor topbar rule as the single sanctioned gradient, Source Serif display + IBM Plex body/mono. Update the action-color list to the post-Task-7 hues (buy-now green, buy-breakout azure #4f8ff0, breakout-watch amber, pullback violet #5b5fc7, avoid red, wait gray). Keep anti-references (cyan-purple gradients, glassmorphism, Inter-only SaaS), drop the now-false "without pure black" and steel-teal wording.
- [ ] **Step 2:** AGENTS.md: add "Feedback loop" section — outcomes flow (paper_ledger close → findings + live_adapt + rank blend), promotion queue rules (manual approve only), scheduler operation.
- [ ] **Step 3:** Commit — `docs: codify BMW M design system; document feedback loop and scheduler`

### Task 17: End-to-end verification

**Complexity:** standard (browser-driven)

- [ ] `.venv/bin/python -m pytest tests/ -v` — full suite green (new + pre-existing `tests/evolve_v1`, `tests/market_runtime`).
- [ ] `cd apps/trade-desk && npm run build` — zero errors.
- [ ] Dev server checks (use the Browser pane / preview tools, take screenshots):
  - `/?symbol=MU`, account 10000, Risk % 0.5 → VerdictPanel shows **risk ≈ $50** and "0.50%" (the headline fix).
  - `/gamma?symbol=MU` → flip strike near spot; wall distances single-signed sane percents; expected move "±x.x%"; legend colors all distinct; bullish elements green.
  - `/options?symbol=APLD` → mode badge tint visible.
  - `/leaderboard` → live columns render; provisional muting for low-n models.
  - `/evolve` → promotion queue panel (empty state or entries); phase separators visible.
- [ ] `.venv/bin/python tools/evolve_scheduler.py --once` → clean log, no approve calls (`grep -c approve tools/evolve_scheduler.py` → 0).
- [ ] Report results with screenshots; fix anything found before the final whole-branch review.

---

## Execution notes for the controller (subagent-driven-development)

- Branch first (`prod-ready-v1`); ledger at `.superpowers/sdd/progress.md`.
- Task order matters within Phase A (Task 2 depends on Task 1's fraction semantics). Phases B and C are independent of each other after A.
- Model tiers: Tasks 4, 7, 8, 9, 11, 16 → cheap; Tasks 1, 2, 3, 5, 6, 10, 13, 14, 15, 17 → standard; Task 12 → most capable (promotion safety).
- Copy the Global Constraints block verbatim into every reviewer dispatch.
- Known open question for implementers to resolve-and-report (not block): exact trials.jsonl row schema for the dedupe key (Task 14) and whether analyze states carry an `entry` key (Task 4).
