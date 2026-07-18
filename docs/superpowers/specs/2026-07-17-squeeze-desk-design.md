# Squeeze Desk: real-time gamma squeeze engine + /gamma rebuild

**Date:** 2026-07-17
**Status:** Approved design, pending implementation plan

## Goal

Detect bullish and bearish gamma squeezes *as they build* in the live options
chain, score them with an explainable model, prove the model with a live
track record, and present it on a rebuilt `/gamma` page ("Squeeze Desk")
trustworthy enough to sit next to live risk.

## Decisions made (with user)

| Decision | Choice |
|---|---|
| Trust basis | Track record + replay: persist snapshots from day one, log every alert, score against realized moves |
| Feed & cadence | LSE intraday chain (`LSE_API_KEY`), watcher polls every 90s; yfinance fallback = explicit degraded mode |
| Universe | One focus symbol (whatever the desk loads); watcher per symbol |
| Model | Stateful deterministic engine (structural + dynamic components), no ML until real snapshot data accumulates |
| UI scope | Full `/gamma` rebuild around the squeeze; options page gets only a deep-link chip |

## Architecture

New module `services/market_runtime/squeeze/` inside the existing FastAPI
runtime (deploys behind `MARKET_RUNTIME_URL`, follows the StreamSupervisor
background-thread pattern).

```
LSE chain --poll 90s--> SqueezeWatcher (bg thread, one per watched symbol)
                            | snapshot
                            v
                     SqueezeEngine  (pure: prev_state + snapshot -> state)
                        |                        |
                        v                        v
              SQLite store                in-memory state
        (snapshots, alerts, outcomes)            |
                                                 v
Next.js /api/squeeze/[...path] proxy  <---  FastAPI endpoints
        ^
   /gamma page polls ~20s
```

- **Shared GEX math**: extract the pure computation (BS gamma, walls, flip,
  structural squeeze score) from `tools/gamma_exposure.py` into
  `tools/gex_core.py` (tools/ is already on the runtime's `sys.path`). The
  CLI script keeps working and imports the same functions. One source of
  truth.
- **Watch lifecycle**: desk sends `POST /squeeze/watch {symbol}` every 60s
  while the page is open (idempotent heartbeat). No heartbeat for 5 min ->
  watcher stops. Bounded API usage by construction.
- **Fast reads**: `GET /squeeze/state/{symbol}` serves in-memory state —
  no per-request Python spawn (removes the current 90s worst case).

## The model: Squeeze Engine v2

### Inputs per poll (LSE chain)
Per-contract gamma, `volume_today`, `premium_today`, strike, expiry, IV,
underlying price; trusted spot via existing spot resolution.

### Structural score (extracted from existing `_compute_squeeze_score`)
Negative near-spot GEX fuel, call/put wall proximity (expected-move scaled),
OTM concentration, wall asymmetry, expected-move reach, flip distance.
Behavior preserved as-is at extraction time.

### Dynamic score (new — detects "building")
Computed from inter-poll differences over a rolling ~15 min window:

1. **Wall build/erode rate** — d(call_wall_gex)/dt and d(put_wall_gex)/dt,
   normalized by total book gamma.
2. **Flow acceleration** — delta of `volume_today` / `premium_today`
   concentrated in OTM calls vs OTM puts, z-scored against that session's
   own baseline.
3. **Spot kinetics** — EMA of per-minute spot velocity, signed toward the
   relevant wall, scaled by proximity.
4. **IV lift** — ATM IV change over the window (hedging-pressure
   confirmation).

### Combination
`score = clamp(0.5 * structural + 0.5 * dynamic, -100, +100)`.
Weights are constants in one config dataclass and are **recorded on every
snapshot**, so accumulated outcome data can recalibrate them later without
ambiguity about what produced historical scores.

### Phase state machine (per direction, hysteresis + min dwell)
- `NONE -> BUILDING`: score >= +25 (<= -25 bear) AND rising for >= 2
  consecutive polls.
- `BUILDING -> PEAKING`: score >= +55 and score momentum flattens.
- `BUILDING/PEAKING -> FADING`: score drops > 15 points from its session
  peak.
- `FADING -> NONE`: |score| < 15.
All thresholds live in the config dataclass. Desk displays phase + duration
("BUILDING · 24 MIN"), never a bare flickering number.

### Confidence (0-100, multiplicative gates — honest by construction)
- Data freshness (age of chain asof)
- Chain quality (contract count, spot/chain price consistency)
- Component agreement (structural and dynamic same direction)
- Track-record factor: neutral until >= 20 resolved alerts, then scales with
  observed hit-rate vs 50% baseline. Confidence is always displayed with its
  evidence count: "unproven (n=7)" until proven.

### Alerts
Emitted on phase transitions only (enter BUILDING, enter PEAKING, flip to
FADING). Each alert stores its full component snapshot.

## Track record & replay

- **Storage**: `data_cache/squeeze/{SYMBOL}.sqlite`, tables:
  - `snapshots`: ts, spot, score, phase, components JSON, weights, feed meta
  - `alerts`: id, ts, direction, phase transition, score, spot, components
  - `outcomes`: alert_id, horizon, realized return, hit/miss, resolved_at
- **Horizons**: 30 min and 2 h, capped at market close.
- **Hit definition (v1 constants, documented, tunable)**: signed spot return
  in alert direction >= 0.2% (30 m) / 0.5% (2 h).
- **Resolution**: evaluator uses the watcher's own recorded spot series (no
  extra API calls). Watch stopped early -> lazy resolution on next watch via
  yfinance 1-minute backfill; still pending after close -> resolve at close.
- **Ledger stats**: n alerts, resolved count, hit-rate per direction x
  horizon, average favorable move, worst adverse move.
- **Replay harness**: `python -m services.market_runtime.squeeze.replay
  --symbol X [--date ...]` re-runs stored snapshots through the engine.
  Doubles as the regression suite for any future scoring change.

## API

FastAPI (market_runtime):

| Endpoint | Purpose |
|---|---|
| `POST /squeeze/watch` `{symbol}` | Start/refresh watcher (idempotent heartbeat) |
| `GET /squeeze/state/{symbol}` | Score, phase + duration, confidence + evidence count, components, walls/flip/spot, session timeline (decimated), ledger summary |
| `GET /squeeze/ledger/{symbol}` | Full alert history with outcomes |

Next.js: one thin proxy route `apps/trade-desk/src/app/api/squeeze/[...path]/route.ts`
forwarding to `MARKET_RUNTIME_URL` (dev default `http://localhost:8000`,
matching the Dockerfile/uvicorn port). The proxy attaches
`MARKET_RUNTIME_API_TOKEN` server-side, reusing the existing pattern in
`tradeDesk.ts`. Browser stays same-origin; identical local and deployed.

**Degraded mode**: no LSE key -> structural-only score from yfinance OI,
badge `DEGRADED — EOD OI data`, dynamics panel states why it is empty.

## UI: /gamma becomes the Squeeze Desk

Institutional terminal per repo design rules: steel teal brand, Source Serif
display numerals, IBM Plex mono data, action-color law, dense but legible,
no gradients/glow.

Layout (top to bottom):

1. **Command bar** — symbol input, feed badge (`LSE LIVE` pulse / `DEGRADED`
   / `STALE`), poll age, expiry filter. The LED is the honesty anchor.
2. **Hero band** — left: bipolar squeeze meter (-100..+100), horizontal
   needle gauge, phase-colored zones, large score, phase line
   (`BULLISH SQUEEZE — BUILDING · 24 MIN`). Right: confidence number +
   evidence tag + one line of operator English ("Pressure building into the
   32 call wall. Fuel: -$1.8B near-spot GEX. Flow accelerating in OTM
   calls.").
3. **Session timeline** — full-width score sparkline for the day, phase
   bands tinted per action colors, alert tick markers. The "watch it build"
   element.
4. **Strike ladder (wall map)** — replaces 3D `GammaScene` in the main flow:
   vertical strike axis, per-strike GEX bars (calls vs puts), moving spot
   line, walls highlighted with live build/erode arrows (d/dt), flip level
   dashed. `GammaScene.tsx` stays in the repo but is no longer rendered on
   this page.
5. **Component attribution** — signed horizontal bars for all structural +
   dynamic components. No black box.
6. **Track record card + alert ledger** — hit-rate 30m/2h with n, avg move
   after alert, dense mono table of alerts (hit / miss / pending). Honest
   empty state: "No resolved alerts yet — the ledger builds while you
   watch."

Polling: page refreshes state every ~20s and heartbeats the watch every 60s.
Transitions animate 200ms ease, no bounce. Options page: a single deep-link
chip to the Squeeze Desk.

## Error handling

- Missing LSE key -> explicit degraded mode (structural only, labeled).
- Poll failure -> exponential backoff; after 2 consecutive misses the desk
  shows `STALE` and freezes the phase clock. Old data is never presented as
  live.
- Spot/chain divergence -> snapshot rejected and counted; rejection count
  visible in the command bar.
- Every failure states its cause in the UI (honest empty states principle).

## Testing

- **Engine (pure)**: synthetic snapshot sequences — bull build, fade,
  whipsaw — assert phase transitions, hysteresis (no flapping), score
  bounds, component attribution sums.
- **Evaluator**: synthetic spot paths — hit/miss thresholds, close capping,
  lazy resolution.
- **Store**: SQLite round-trips for snapshots/alerts/outcomes.
- **API**: FastAPI TestClient — watch lifecycle (heartbeat expiry), state,
  ledger, degraded mode.
- **UI lib**: formatting and phase-to-color mapping tests alongside existing
  `*.test.ts` suites.
- **Replay harness** is the model regression suite going forward.

## Out of scope (explicit)

- Multi-symbol watchlist / background scanning (engine is designed so a
  watchlist can drop in later; not built now).
- ML-trained classifier or learned weights (requires accumulated snapshot
  data; the schema records everything needed to train later).
- Trade execution or order routing from the Squeeze Desk.
- Historical chain backfill purchases (no free source exists).
