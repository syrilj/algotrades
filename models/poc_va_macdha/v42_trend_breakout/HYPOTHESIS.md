# v42_trend_breakout Hypothesis

If a model only enters when price is already above the anchored VWAP, in a squeeze-release expansion, and with positive momentum, it will generate a signal set that is materially less correlated with `v39b_live_adapt` because it avoids the pullback/POC-VAL mean-reversion entries that `v39b` specializes in.

The trade-off is fewer entries and later entry timing, but the ensemble benefit from lower correlation should outweigh the standalone return gap.

## Test criteria

1. Signal correlation with `v39b_live_adapt` < 90%.
2. Positive total return on the `EQUITY_WINNER_BAG`.
3. When added to `v41_ensemble_feedback`, the combined `perf_weighted` or SGD ensemble improves over the `v39b` + `v39d` baseline.
