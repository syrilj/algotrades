# v49 precision trend

`v49_precision_trend` is a high-precision challenger to `v39d_causal`, not a
promotion candidate.  It accepts a complete causal trend entry episode only
when at least five of eight pre-registered quality checks are true: relative
strength, volume participation, prior candle direction, volatility state,
distance from value, MACD state, trend separation, and recent reversal state.

The gate is intentionally fixed at five before its first evaluation.  It may
raise win rate by trading less often, but it must still pass all after-cost
return, drawdown, breadth, and prospective-shadow gates.  A higher win rate
alone never qualifies it for promotion.
