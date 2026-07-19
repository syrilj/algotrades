# v90_meta_confidence

Two-sided (BUY/SELL/FLAT) meta-labeling engine with **calibrated** confidence.
This is the first model in the bundle that (a) issues a real model-driven SELL
signal and (b) exposes an honestly-calibrated probability rather than an ordinal
quality score.

## Architecture

```
OHLCV (1H)
  -> causal features (features.py: returns, RSI, MACD-hist, ATR regime, vol-z,
     EMA stack/cloud, SMA200 trend, realized vol, range position, session hour)
  -> triple-barrier labels (TP/SL = +/-1.0*ATR, time exit = 8 bars);
     win := net-of-cost exit return > 0
  -> XGBoost LONG head + SHORT head (depth 4, 250 trees, lr 0.03)
  -> purged + embargoed 5-fold cross-fit  -> out-of-fold probabilities
  -> isotonic calibration (activated only if OOF Brier AND log-loss improve)
  -> raw score >= threshold decides BUY / SELL / FLAT;
     calibrated probability is the confidence shown to the operator
```

Artifacts (produced by `tools/train_v90_meta_confidence.py`):
`meta_xgb_long.json`, `meta_xgb_short.json`, `calibration.json`,
`thresholds.json`, `results.json`.

Data: yfinance `auto_adjust` 1H bars, 2024-07 → 2026-07 (see `data_cache/1h`).
Contract: train 2024-08-01→2025-08-01, locked holdout 2025-08-01→2026-07-11,
universe TSLA/MU/SPY/IONQ/APLD/XLP/QQQ, 5bp+5bp roundtrip cost.

## Calibration (the honest part)

Isotonic calibration is active for both heads and materially improves reliability:

| head | Brier (raw→cal) | log-loss (raw→cal) | OOF ECE |
|------|-----------------|--------------------|---------|
| long  | 0.2594 → 0.2491 | 0.7140 → 0.6913 | ~0 |
| short | 0.2599 → 0.2495 | 0.7145 → 0.6920 | ~0 |

Holdout (long head): Brier 0.250, log-loss 0.692, **ECE 0.0048** — i.e. when the
model says 55%, it wins ~55% of the time.

## Holdout results (locked OOS, two-sided, after costs)

| operating point | raw thr | n | long/short | win rate | Wilson 95% | avg net/trade | profit factor |
|-----------------|--------:|--:|:----------:|:--------:|:----------:|:-------------:|:-------------:|
| active (top 10%)    | 0.629 | 320 | 223/97 | 51.2% | [46%, 57%] | −0.05% | 0.94 |
| balanced (top 5%)   | 0.671 | 111 | 76/35  | 55.0% | [46%, 64%] | +0.17% | 1.17 |
| selective (top 2%)  | 0.724 |  34 | 20/14  | 58.8% | [42%, 74%] | +0.82% | 2.26 |
| sniper (top 1%)     | 0.760 |  11 |  6/5   | 63.6% | [35%, 85%] | +1.60% | 7.06 |

Thresholds are derived from **train** OOF quantiles (no holdout peeking).

## Honest read — do not overclaim

- **The real, calibrated win-probability ceiling on this universe/timeframe is
  ~52–65%, not the 86–91% headline win rates advertised by older bundles.** Those
  came from 33–52 trades and dropped ~8–10pp out-of-sample. v90's edge is a
  *positive-expectancy asymmetry* (winners larger than losers, PF > 1 at
  selective thresholds), not a high hit-rate.
- Expectancy is positive and improves as you tighten the threshold, but sample
  size shrinks and the win-rate confidence interval widens. At the `selective`
  and `sniper` points the Wilson lower bound is still below 50% — treat those
  win rates as suggestive, not proven.
- This is **simulated only**. No live-profitability claim is made. The next gate
  is forward paper/shadow trading before any real capital.

## Runtime behaviour

`SignalEngine.generate(data_map)` returns signed target weights (positive = BUY,
negative = SELL when `allow_short=true`, else short becomes a flatten/avoid
signal), and exposes `last_confidence` (calibrated P(win)) and `last_side`
(BUY/SELL/FLAT) per symbol. **Fail-closed:** if any artifact is missing or
xgboost is unavailable, it returns FLAT everywhere with zero confidence.

## Not promoted

v90 is **not** wired into `DEPLOYMENT_MANIFEST.json`. Promotion requires clearing
the existing fail-closed gates and a forward paper-trading window first. The
promoted book remains `v72_dual_sleeve`.
