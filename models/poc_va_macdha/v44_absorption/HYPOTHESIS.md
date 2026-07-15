# Hypothesis

**Version:** `v44_absorption`  
**Family:** `poc_va_macdha`  
**Parent:** `v39d_confluence` (WINNER on source=local)  
**Date:** 2026-07-14

## Claim

The Pine OrderFlow Absorption Matrix carries information about **volume effort, delta bias and wick absorption** that the v39b VPA stack does not explicitly model. The repository only has OHLCV bar data, so the lower-timeframe delta and true absorption side cannot be replicated exactly. We can approximate the usable pieces with OHLCV-safe transforms:

1. **Candle-delta proxy** for LTF CVD: `volume * sign(close - open)`
2. **Wick absorption** volume: `volume * wick / range` on the side of the move
3. **Volume / delta percentile clusters** (small / medium / whale) with point-in-time quantiles
4. **Composite flow score** from imbalance, CVD bias, absorption bias and last cluster direction

These four features are added to the XGB meta classifier. The order-flow signal is used only as an XGB feature (no `adj_proba` boost) after ablation showed the boost raised drawdown.

## Pass bar

Reconcile on `source=local` 1H WINNER bag (2024-08-01 to 2026-07-11, $1,000) vs `v39d_confluence` (or `v39b_live_adapt`):

- **Promote** if full Sharpe ≥ v39d − 0.03 **and** (full return ≥ v39d or early Sharpe ≥ v39d) with n ≥ 100
- **Soft keep** if DD improves and Sharpe ≥ 2.4 with n ≥ 100
- **Kill** if full return drops > 20% relative to v39d without a Sharpe/DD improvement

## Final result

Run `tools/train_v44_meta.py --seed --retrain` on `source=local` 1H WINNER bag:

| model | return | max DD | Sharpe | n | final |
|-------|--------|--------|--------|---|-------|
| `v39b_live_adapt` | +309.7% | -13.1% | 2.70 | 141 | $4,097 |
| `v39d_confluence` | +357.5% | -13.4% | 2.82 | 135 | $4,575 |
| `v44_absorption`  | +262.7% | -17.8% | 2.24 | 158 | $3,627 |

**Verdict: do not promote.** `v44_absorption` underperforms both parents on return, Sharpe and drawdown. The OHLCV approximation of order-flow delta/absorption is too noisy and does not add enough edge to justify the extra drawdown. Keep as a research artifact; the feature module can be reused if higher-fidelity tick/bid-ask data becomes available.

## Live use

```bash
.venv/bin/python tools/train_v44_meta.py --seed --retrain
```
