# Hypothesis

**Version:** `v60_microstructure`  
**Family:** `poc_va_macdha`  
**Date:** 2026-07-14

## Claim

Large institutional executions (TWAP/VWAP/POV-style slicing and absorption of passive liquidity) leave detectable footprints in OHLCV bar data. The footprints are strongest in liquid equities during shallow pullbacks within established uptrends:

1. **Order-flow imbalance (OFI) proxy** — signed volume from candle delta + tick rule, showing persistent one-sided aggressive flow.
2. **Absorption / stealth footprint** — high volume relative to small price movement, normalised by ATR and volume regime.
3. **Volume schedule deviation** — intraday cumulative volume deviating from a historical TWAP-like profile.
4. **VPIN-style toxicity** — volume-bucketed average absolute imbalance.
5. **VPA confirmation** — volume-price agreement with close location within the bar.
6. **Regime context** — long-term trend, VWAP distance, volatility regime, RSI, and time-of-day controls.

A gradient-boosted classifier is trained on triple-barrier labels to predict the probability of a successful long trade. A high-precision threshold (meta-labeling) only acts on the highest-conviction setups.

## Pass bar

Reconcile on `source=local` 1H WINNER bag (2024-08-01 to 2026-07-11, $1,000):

- **Promote** if full Sharpe ≥ 2.5, return competitive with `v39d_confluence`, and walk-forward OOS (train 2024-08 → 2025-08, test 2025-08 → 2026-07) remains positive with win-rate > 50%.
- **Keep as research artifact** if in-sample is promising but OOS degrades or drawdown is > 25%.
- **Kill** if full return < 0% or OOS is negative after accounting for costs.

## Results

| model | mode | return | max DD | Sharpe | n | wr | final |
|-------|------|--------|--------|--------|---|----|----|
| `v39d_confluence` | daily | +357.5% | -13.4% | 2.82 | 135 | 67% | $4,575 |
| `v60_microstructure` (in-sample, full) | daily | +639.4% | -21.8% | 2.69 | 105 | 62% | $7,394 |
| `v60_microstructure` (walk-forward OOS) | daily | +14.8% | -13.7% | 0.26 | 13 | 38% | $1,148 |

**Verdict: research artifact, not promoted.** The full-history (in-sample) run is strong but the walk-forward OOS degrades significantly (38% win-rate, underperforms buy-and-hold). This is consistent with the hypothesis that OHLCV-only proxies of order-flow and absorption are too noisy to sustain the targeted high precision out-of-sample. The feature module and training pipeline are retained for future refinement with tick/bid-ask or Level-2 data.

## Research notes

- The XGB classifier trained on triple-barrier labels produces tightly clustered probabilities (mostly 0.48–0.56), limiting the achievable precision of the meta-labeling threshold.
- The `min_conviction` threshold was tuned to 0.55 for in-sample; OOS win-rate suggests overfitting to the training distribution.
- Live execution would require smart routing and adaptive slicing; the model is not ready for live deployment.

## Desk

Run with `mode="daily"`:

```python
import dynamic_model_rank as dmr
CODES = ["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "XLP.US", "QQQ.US"]
model = dmr.discover_models(["v60_microstructure"])[0]
dmr.run_one(model, mode="daily", codes=CODES, start="2024-08-01", end="2026-07-11", tag="final", cash=1000, source="local", interval="1H")
```

Retrain the XGB meta-classifier:

```bash
.venv/bin/python tools/train_v60_microstructure.py --retrain
```
