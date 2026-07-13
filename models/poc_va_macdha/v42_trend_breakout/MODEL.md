# v42_trend_breakout

Trend-continuation / breakout teacher designed to be less correlated with `v39b_live_adapt`.

## Philosophy

`v39b` is a react-not-predict engine that buys volume-confirmed pullbacks and demand-node retests. `v42` does the opposite: it only takes long entries when price is already in an established uptrend, above VWAP, with volume expansion and squeeze momentum positive. The goal is to capture the continuation leg that `v39b` often misses, rather than the mean-reversion entry.

## Key routing

- `signal_tf`: 1h
- `require_vwap_uptrend`: True
- `require_above_vwap`: True
- `require_volume_expand`: True
- `require_sqz_release`: True
- `require_mom_pos`: True
- `exit_below_vwap`: True
- `exit_on_val_break`: True
- `exit_on_sqz_neg`: True
- `soft_confidence`: True

## Metrics target

Correlate <90% with `v39b_live_adapt` while remaining profitable enough to contribute to a `v41` ensemble.
