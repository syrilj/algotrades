# Trump-era live risk model — performance report

**Window:** 2025-01-20 (Trump second inauguration) → 2026-07-11 (local bar end ≈ 2026-07-10)  
**Contract:** `source=local`, `interval=1H`, cash `$1,000`, codes = `EQUITY_WINNER_BAG`  
`["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "XLP.US", "QQQ.US"]`  
**Entry path:** `tools.dynamic_model_rank.run_one`  
**Date of bakeoff:** 2026-07-15 (agent run)

## 1. Multi-pipeline leaderboard

| Model | Role | Return | Max DD | Sharpe | Trades | Win rate | Final $ |
|-------|------|--------|--------|--------|--------|----------|---------|
| **v39b_live_adapt** | Champion baseline (live-adapt teacher) | **+179.1%** | **-12.9%** | **2.68** | 95 | 68.4% | **$2,791** |
| **v39d_confluence** | Champion baseline (equity teacher) | +164.7% | -13.1% | 2.70 | 94 | 67.0% | $2,647 |
| **v72b_trump_risk_soft** | Pipeline B: v39b + soft size + crypto corridor | +148.1% | **-12.9%** | 2.58 | 96 | **68.8%** | $2,481 |
| **v72_trump_risk_hard** | Pipeline A: v39d + hard stand-aside | +146.5% | -13.1% | 2.54 | 96 | 66.7% | $2,465 |

Primary metrics are finite and from completed `dmr.run_one` runs (see `runs/poc_va_dynamic_rank/runs/*/trump_era_live__daily__c1000/artifacts/metrics.csv`).  
Repeat launch of `v72_trump_risk_hard` (`tag=trump_era_live_repeat`) reproduced **identical** metrics (ret 1.465, dd −0.131, sharpe 2.535, n=96, final $2,465).

### Live recommendation

**For live trading with explicit risk-off / size-down (this goal):** prefer **`v72b_trump_risk_soft`**.

- Best max DD among risk overlays (ties v39b at −12.9%).
- Soft continuous sizing still allows residual exposure (floor 15%) so the desk is not binary-flat on every stress tick.
- Optional **COIN/MSTR** corridor term activates only when those symbols are in `data_map` (not required on the winner bag).
- Exposes `last_risk_score` / `last_size_mult` on the engine for live operators.

**If pure Trump-window PnL is the only objective:** stay on **`v39b_live_adapt`** (or `v39d_confluence`). The risk overlays **did not beat** either champion on return in this window; hard stand-aside paid ~18pp of return vs v39d for almost no portfolio max-DD improvement. Treat v72* as **live risk instrumentation + partial crash insurance**, not a promoted alpha replacement.

## 2. Risk-off design (what the model does)

Shared causal sensors (`models/poc_va_macdha/_shared/drawdown_risk.py`):

| Sensor | Contract |
|--------|----------|
| SPY drawdown-from-peak | `price / cummax − 1` |
| SPY vol spike | rolling std of **lagged** returns / expanding median of prior vol |
| SPY trend break | lagged close &lt; SMA50 of lagged closes |
| QQQ drawdown | same as SPY, optional tech stress |
| COIN/MSTR (soft only) | proxy crypto DD × rolling corr to SPY (lagged returns) |

**Pipeline A (hard):** `risk_score ≥ 0.55` → size multiplier **0** (stand aside). Teacher = `v39d_confluence`.  
**Pipeline B (soft):** continuous mult `(1 − score)^power` in `[0.15, 1]`. Teacher = `v39b_live_adapt`. Crypto weight 0.10.

Unit tests (`tests/test_drawdown_risk.py`): elevated synthetic crash → lower/zero size; calm series → teacher size retained. 8/8 passed.

## 3. Named large-drawdown / crash-like episodes

Judgments use **point-in-time** hard risk state *before* / *through* trough — not hindsight peak labels.

| Episode | Trough | Asset path | Pre-elevated (5d) | During elevated | Hard mult @ trough | Soft mult @ trough | Judgment |
|---------|--------|------------|-------------------|-----------------|--------------------|--------------------|----------|
| Liberation-Day / tariff selloff | 2025-04-08 | SPY ~−18.9% peak-to-trough | 0% | **57%** | **0.0** | 0.15 | **partial** |
| Late-Nov 2025 pullback | 2025-11-20 | SPY ~−5.1% | 0% | 0%* | **0.0** | 0.36 | **partial** |
| Mar 2026 correction | 2026-03-30 | SPY ~−9.1% | 0% | 27% | **0.0** | 0.44 | **partial** |
| COIN crypto-proxy collapse | 2026-02-12 | COIN deep DD (bag does not trade COIN) | 0% | 0% | 1.0 | 0.66 | **missed** (SPY sensors) |
| MSTR crypto-proxy grind | 2026-06-26 | MSTR ~−82% window max DD | 0% | 5% | 1.0 | 0.71 | **missed** (SPY sensors) |

\*Nov trough bar itself hit score 0.68 → mult 0, but the short 4-day window spent little time above threshold before the low.

### Reading the audit

- **Equity index crashes (Apr-2025, Mar-2026):** risk-off **did fire by the trough** (hard mult = 0). It was **late** (little pre-emptive elevation in the 5 days before episode start) → honest label **partial**, not “caught early.”
- **Meme / crypto-proxy crashes (COIN, MSTR):** SPY-centric hard gate **does not** stand aside when only crypto-linked names implode while SPY is calm → **missed**. Soft’s crypto term helps only if COIN/MSTR are loaded into `data_map` and corr is high; on the equity winner bag alone, that term is inactive.
- Portfolio max DD of v72* stayed near champion (~13%) because the bag’s path DD is not identical to SPY’s −19% index path (position sizing, selection, and exits already limit some damage).

## 4. Correlation / crypto-corridor findings

Local `data_cache/1h` has **no raw BTC series** and **no VIX**. Proxies used: **COIN**, **MSTR** (plus SPY/QQQ).

| Pair (20-bar corr of **lagged** returns, Trump window) | Mean |
|--------------------------------------------------------|------|
| SPY–QQQ | **0.93** |
| SPY–COIN | **0.54** (rises to **0.82** in Mar–Apr 2025 stress) |
| SPY–MSTR | **0.47** (rises to **0.76** in Mar–Apr 2025 stress) |

**Kept:** SPY DD/vol/trend; QQQ DD; soft-only COIN/MSTR DD × corr gate.  
**Discarded:** unlagged same-bar corr; full-sample z-scores; raw BTC/VIX (missing); hard crypto stand-aside on bag-only runs (would be inactive noise).

## 5. How it would perform “live right now”

Interpretation for a desk running this from inauguration to mid-2026 on the winner bag:

1. **Alpha remains the teacher.** Overlays reduce gross return ~16–33pp vs teachers.
2. **Hard risk-off is a binary kill-switch** when SPY/QQQ stress scores spike — useful when the operator wants automatic flat on index crash regimes (Apr-2025 trough = flat).
3. **Soft risk-off** is better for live *feel*: size bleeds down continuously; crypto corridor can attach when COIN/MSTR are watched.
4. **Do not expect omniscient crash prediction.** Episode audit is majority **partial** / **missed** on crypto-specific blowups. Sensors reduce exposure *into* index stress; they do not forecast every meme crash.
5. **Live wiring:** models are discoverable via `dmr.discover_models(["v72b_trump_risk_soft"])`; no brokerage routing changes. Optional next step (out of scope here): surface `last_risk_score` on trade-desk analyze.

## 6. Data coverage inventory

| Series | 1H cache | Range |
|--------|----------|-------|
| Winner bag (TSLA, MU, SPY, IONQ, APLD, XLP, QQQ) | yes | 2024-07-11 → 2026-07-10 |
| COIN, MSTR (crypto proxies) | yes | same |
| BTC / ETH / VIX | **no** in `data_cache/1h` | — |

## 7. Reproduction

```python
import tools.dynamic_model_rank as dmr
from evolve.farm import EQUITY_WINNER_BAG

m = dmr.discover_models(["v72b_trump_risk_soft"])[0]  # or v72_trump_risk_hard
dmr.run_one(
    m, mode="daily", codes=EQUITY_WINNER_BAG,
    start="2025-01-20", end="2026-07-11",
    tag="trump_era_live", force_1d=False, cash=1000,
    source="local", interval="1H",
)
```

```bash
PYTHONPATH=tools:. .venv/bin/python -m pytest tests/test_drawdown_risk.py -v
```
