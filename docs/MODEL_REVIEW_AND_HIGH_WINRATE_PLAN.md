# Model Review & High-Win-Rate Live-Signal Plan

**Date:** 2026-07-19
**Scope:** Full review of the `poc_va_macdha` model family, honest assessment of the
current promoted book, and a concrete design for a model that can emit **confident
two-sided (BUY / SELL) signals during live sessions**.

> This is a research/design document. Every number quoted from the repo is a
> **simulated backtest**, not live results. Nothing here is financial advice.

---

## 1. What exists today (inventory)

- **128 versioned engines** under `models/poc_va_macdha/v*` plus `v65_spec_*`
  per-symbol specialists and options families under `models/poc_va_gex/`.
- **Promoted live book:** `v72_dual_sleeve` — a hierarchical merge of
  `v71_live_confidence` (high-WR mean-reversion "sniper") and `v39d_confluence`
  (return/Sharpe "core"). See `models/poc_va_macdha/DEPLOYMENT_MANIFEST.json`.
- **Fallback chain (fail-closed):** `v39d_confluence` → `v71_live_confidence` →
  `v39b_live_adapt`; rollback = `v39d_confluence`.
- **Runtime:** `services/market_runtime/` streams completed bars and generates
  tickets; `tools/live_plan.py` produces the desk's BUY/SELL/FLAT plan.
- **Governance:** SHA256-pinned manifest, walk-forward + locked holdout,
  deflated Sharpe, Wilson CIs, Platt/isotonic calibration gates.

Reference contract (`DEPLOYMENT_MANIFEST.json`): 7 symbols
(TSLA, MU, SPY, IONQ, APLD, XLP, QQQ), 1H bars, train `2024-08-01→2025-08-01`,
locked holdout `2025-08-01→2026-07-11`, 5 bp slippage + 5 bp commission.

---

## 2. Honest assessment of the current models

### 2.1 The system is long/flat only — it has **no real SELL signal**

Every promoted `SignalEngine.generate()` returns a target weight in `[0, cap]`
(long or flat). There is no short/negative target and no explicit "exit now"
signal separate from "position went to 0". Examples:

- `v72_dual_sleeve/signal_engine.py` clips all weights to `[0, max_weight]`.
- `v50_high_win_rate/signal_engine.py` emits `1.0` or `0.0` × `signal_scale`.
- `v39d_confluence/signal_engine.py` is a long-confluence engine.

The desk can *display* a `SELL`/`short` verdict (`tools/live_plan.py` lines
~331, ~482–508 read `go_short`/`soft_short`), but that comes from the analysis
layer, **not** from the promoted model. The comment at `live_plan.py:487` is
explicit: "equity path is long-only — never invent a short bias."

**Implication for the ask:** "actively give me sell and buy signals during live
sessions" is *not* something the current promoted model can do honestly. A SELL
today just means "flatten a long," and shorting is not modeled or backtested at
all. This is the single biggest gap between what you asked for and what exists.

### 2.2 The "high win rate" numbers are real but statistically thin

| Model | Full WR | Trades (n) | OOS WR | OOS n | Wilson 95% low @ full n |
|-------|--------:|-----------:|-------:|------:|------------------------:|
| `v70_high_confidence_wr` | 90.9% | 33 | — | — | ~76% |
| `v50_high_win_rate` | 86.5% | 52 | 77.8% | 27 | ~74% |
| `v71_live_confidence` | 86.0% | 50 | 76.9% | 26 | ~73% |
| `v72_dual_sleeve` (promoted) | 72.1% | 179 | 65.5% | 84 | ~65% |

Two things stand out:

1. **The highest win rates come from the fewest trades.** A 91% WR on 33 trades
   has a Wilson 95% lower bound near 76%; on the ~9-symbol/1-year OOS slice the
   effective sample is even smaller. `v50/MODEL.md` and the README both already
   admit the auditor flags these as `below_claim_n` / research-only. The repo is
   honest about this — but it means "86–91% win rate" is **not** a bankable live
   expectation, it is a wide interval.

2. **Win rate degrades out-of-sample** (86%→77%, 87%→78%, 72%→66%). That ~8–10pp
   OOS haircut is the realistic drift you should budget for live.

### 2.3 Win rate is the wrong headline metric for mean-reversion snipers

The high-WR sleeves (`v45_ultimate_rsi` → `v50`/`v71`) are oversold-bounce
mean-reversion. That style structurally produces **many small wins and rare large
losses** (you win the bounce often, but the trade that keeps falling is a big
loser). A high win rate with negative skew can still be flat or negative in
expectancy after costs. The repo already carries 5 bp + 5 bp cost stress, which
is good, but the promotion evidence emphasizes WR and Sharpe over
**expectancy per trade (avg R)** and **tail/skew**, which matter more for a book
you intend to trade live for confidence.

### 2.4 Confidence is explicitly NOT calibrated — probability sizing is blocked

`DEPLOYMENT_MANIFEST.json`:

```json
"calibration": { "status": "blocked_identity_ordinal_only",
                 "probability_calibrated": false, "cross_fitted": false },
"execution_readiness": {
  "probability_sized_execution": "blocked_until_cross_fitted_calibrator_passes",
  "reason": "current v72 artifact is an identity map ..." }
```

So `last_confidence` today is an **ordinal rank, not a probability**. When you
ask for "sell/buy signals with high confidence," the honest state of the system
is: *it cannot currently attach a trustworthy probability to any signal.* This is
the correct, honest posture (`docs/confidence_calibration.md`), but it is also
the exact capability your request needs — and it is unfinished.

### 2.5 Reproducibility / results-file inconsistencies

The per-model `results.json` files were generated with **inconsistent starting
capital**, so they are not directly comparable:

| Model | `total_return` | `final_value` | Implied starting cash |
|-------|---------------:|--------------:|----------------------:|
| `v72_dual_sleeve` | 5.131 | 6,130 | ~$1,000 |
| `v71_live_confidence` | 1.140 | 2,140 | ~$1,000 |
| `v39d_confluence` | 3.108 | 4,107,761 | ~$1,000,000 |
| `v50_high_win_rate` | 1.088 | 2,087,869 | ~$1,000,000 |
| `v70_high_confidence_wr` | 0.433 | 1,433,047 | ~$1,000,000 |
| `v85_anti_overfit` | 1.635 | 2,635,305 | ~$1,000,000 |

The `data_contract` says `cash: 1000`, but four of six files were clearly run at
$1M. Also `v39d` full return is `3.108` here vs `+357%` (3.57) in
`v72/MODEL.md`. None of this changes the models, but it means the headline
tables mix runs and should be regenerated from one contract before trusting
cross-model comparisons.

### 2.6 Overfitting surface is large

- **128 versions** searched over **one 7-symbol basket** in **one regime**
  (a 2024–2026 bull/AI melt-up). Deflated Sharpe helps discount best-of-N, but
  selecting a champion after 100+ trials on the same window and universe is a
  strong data-mining prior. The `v85_anti_overfit` doc already concedes its
  intervals "do not support an 80–90% win-probability claim."
- **Regime concentration:** IONQ/APLD-style names drove the fat right tail (see
  `docs/additional/MODEL_IMPROVEMENT_PLAN.md` §6). A model tuned on that tail is
  fragile if the AI-momentum regime cools.
- **Symbol-specific hard-codes** in `v39d` `_ROUTING` (per-ticker params) fit the
  in-sample tape and may not transfer.

### 2.7 Other gaps (from `MODEL_IMPROVEMENT_PLAN.md`, still open)

- Options/GEX layer has no historical OI → cannot be honestly backtested.
- No per-trade feature logging feeding the meta-model in a closed loop.
- Fixed universe; no live/paper track record yet (all evidence is simulated).

---

## 3. What "high win rate in live trading with confident buy & sell signals"
actually requires

Being blunt so the target is real, not marketing:

1. **A calibrated probability**, not an ordinal score. "High confidence" must mean
   "when the model says 80%, it wins ~80% of the time OOS." That needs the
   cross-fitted calibrator the manifest is currently blocking on.
2. **Two-sided signals** (long AND short/flatten) that are *backtested as such*,
   with costs, borrow, and the fact that shorting has different risk.
3. **Expectancy > 0 after costs**, with acceptable skew — not just WR > X%.
4. **A decision threshold that trades WR against frequency.** You can have 85% WR
   at 30 trades/yr, or 62% WR at 300 trades/yr. "Actively during live sessions"
   implies you want frequency; that pulls WR down. Pick the operating point on
   purpose.
5. **Live/paper validation** before believing any of it. No amount of backtest
   replaces a forward paper track record.

There is no model that is simultaneously (a) high win rate, (b) high frequency,
(c) high per-trade edge, and (d) robust across regimes. You choose 2–3. My
recommendation below optimizes for **calibrated confidence + honest two-sided
signals at a chosen frequency**, which is the closest achievable version of your
ask.

---

## 4. Proposed model: `v90_meta_confidence` (design)

A meta-labeling classifier on top of the existing frozen engines that outputs a
**calibrated probability** and a **direction**, feeding an explicit
BUY / SELL / FLAT decision with confidence bands. This reuses everything that
already works and adds only the two missing pieces (calibrated probability +
two-sided decisioning).

### 4.1 Architecture

```
Frozen base engines (features/signals, unchanged)
  v39d_confluence (long confluence), v45_ultimate_rsi (mean-rev),
  v71 sniper, VPA/MACD-HA/RSI/regime features
        │  (point-in-time feature vector per bar)
        ▼
Meta-labeling classifier  (Lopez de Prado triple-barrier labels)
  - LONG head:  P(long trade hits +barrier before -barrier)
  - SHORT head: P(short trade hits +barrier before -barrier)
  - gradient-boosted trees (XGBoost, matches existing meta_xgb_final.json)
        ▼
Cross-fitted probability calibration (isotonic/Platt, purged K-fold)
  - only activate if OOS Brier AND log-loss improve vs raw (existing gate)
        ▼
Decision layer
  p_long, p_short → verdict:
    p_long  >= enter_hi           → BUY  (high confidence)
    p_long  in [enter_lo, hi)     → BUY  (scaled / watch)
    p_short >= enter_hi           → SELL/short (high confidence)
    holding long & p_long < exit  → SELL (flatten)
    else                          → FLAT
  size = f(calibrated p, vol-target)   ← only if calibrator PASSES
```

### 4.2 Why meta-labeling

- It **separates side from size/confidence**: the base engines already decide
  side well; the meta-model's only job is "should I take this signal and how sure
  am I," which is exactly the calibrated-confidence gap.
- **Triple-barrier labeling** (profit-target / stop / time barriers) gives honest,
  path-aware labels and directly optimizes the metric you care about (did the
  trade actually work within the horizon), instead of next-bar sign.
- **Purged, embargoed K-fold** cross-fitting kills the leakage that inflates
  in-sample WR — this is the anti-overfit fix for §2.6.

### 4.3 Getting the SHORT side honestly

- Symmetrize the mean-reversion/confluence features (overbought/`upthrust`/
  `topping_volume`/bear EMA stack already exist in `v39d`'s
  `volume_price_state`/`ema_cloud_state`) into a short candidate generator.
- Backtest shorts with a borrow/short-cost assumption and a hard stop (shorts
  have unbounded tail risk). Gate shorts behind a stricter probability threshold
  than longs.
- If shorting is out of scope for your broker/account, ship the SHORT head as a
  **"flatten/avoid"** signal instead — same model, no borrow.

### 4.4 Choosing the operating point (WR vs frequency)

Report a **precision/recall curve** of `p` thresholds on the locked holdout and
let you pick, e.g.:

| Threshold `enter_hi` | Est. WR | Trades/yr | Use |
|----------------------|--------:|----------:|-----|
| 0.80 | high | low | "only when very sure" |
| 0.65 | medium | medium | balanced live desk |
| 0.55 | lower | high | "active during every session" |

This makes "high confidence" a dial you set, with the WR/frequency tradeoff
stated up front instead of hidden.

---

## 5. Implementation & validation plan

1. **Fix the evidence base first (no modeling):**
   - Regenerate every `results.json` from one contract (`cash`, universe, window)
     so cross-model tables are comparable; reconcile with the README.
   - Add per-trade feature + outcome logging to the candidate ledger.
2. **Build labels & features:** triple-barrier labels on the 1H bars; feature
   matrix = frozen engine outputs + existing causal features (all point-in-time).
3. **Train `v90` meta-model** with purged/embargoed K-fold; LONG and SHORT heads.
4. **Calibrate** with the existing `tools/calibrate_main_models.py` gate; only
   flip `probability_calibrated: true` if Brier + log-loss + ECE improve OOS.
5. **Evaluate** on the locked holdout: expectancy (avg R), skew, Wilson CI on WR
   at each threshold, deflated Sharpe, cost-stress ±2×.
6. **Promote only through existing gates**; wire the BUY/SELL/FLAT + confidence
   bands into `tools/live_plan.py` and the runtime.
7. **Forward paper trade** for a defined window before any real capital, logging
   calibration drift via the existing `runs/live_confidence/shadow_decisions.jsonl`.

### Success criteria (pre-registered, extend the existing bar)

| Metric | Threshold |
|--------|-----------|
| OOS trades at chosen threshold | ≥ 50 |
| OOS expectancy (avg R) | ≥ +0.15R after costs |
| Calibration: OOS Brier & log-loss | improve vs raw; ECE ≤ 0.05 |
| Wilson 95% lower bound on WR | above your stated minimum |
| Deflated Sharpe | > 0 after best-of-N discount |
| Short book (if enabled) | positive expectancy after borrow + stop |

---

## 6. Reality check / blocker

- **I cannot backtest or train any of this in-session:** the repo gitignores
  `data_cache/` and `runs/`, and there is no committed market data or `yfinance`
  installed. Building `v90` and producing OOS evidence needs the 1H parquet cache
  (or a data source + credentials).
- **Everything the repo reports is simulated.** The most valuable next step for a
  "live win rate" claim is a forward paper-trading log, which no backtest can
  substitute for.

**To proceed to implementation I need one of:** (a) the `data_cache/` 1H parquet
for the universe, or (b) approval + a data source (yfinance/Polygon/etc.) so I can
fetch and rebuild it. With that I can implement `v90_meta_confidence`, produce
calibrated OOS evidence, and wire the two-sided confident signals into the desk.
