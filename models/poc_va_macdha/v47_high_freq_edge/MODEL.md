# v47_high_freq_edge Model Notes

## Goal

High trade count + high profit + controlled risk using a short-horizon 1H mean-reversion edge.

## Architecture

```
1H OHLCV
  │
  ├─→ Ultimate RSI (length=14, smooth=14, RMA → EMA)
  │     red cross under 30  = long entry
  │     green cross over 70 = exit
  │
  ├─→ ATR(14)  → trailing stop at 2.5 × ATR below trade high
  │
  └─→ max_hold_bars=8 → vertical barrier (force recycle)

Output: position size per bar ∈ {0, 1.0}
```

## Why this works

- **1H noise is the edge:** 4H oscillator setups are too sparse. The 1H timeframe provides enough pullbacks to generate a high trade count while the mean-reversion tendency of strong tickers keeps the win rate above 50%.
- **Three exit paths:** the RSI overbought exit captures momentum runs; the ATR trailing stop protects against reversals; the `max_hold_bars` barrier recycles capital if neither of the first two triggers.
- **No trend filter:** tests on `1D`, `4H`, and `1H` EMAs filtered out the very oversold bars where the mean-reversion edge lives. The oscillator itself is the sufficient condition on this window.

## Meta-Strategy alignment

| Framework Stage | Implementation in this model |
|-----------------|------------------------------|
| Data            | 1H bars (`source=local` adjusted prices) |
| Labeling        | Triple-barrier: upper/lower/vertical |
| Meta-labeling   | Rule-based confidence (trend + volume) available but disabled in production tune |
| Validation      | Single backtest; purged CV / OOS required before scaling |
| Bet sizing      | Position size from confidence score (default 1.0) |
| Risk control    | ATR trailing stop, max-hold vertical barrier, overbought RSI exit |

## Tuning notes

- The `max_hold_bars` barrier is the strongest lever for trade count. Too short (`4`) and transaction costs + whipsaws dominate; too long (`16`) and the engine gives back too much before the next cycle.
- `atr_mult=2.5` balances stop distance with profit expectation. Lower (`1.5`) stops out too often; higher (`3.5`) lets losers run.
- `use_tp` is disabled. The RSI overbought exit and ATR stop are sufficient; an explicit take-profit was not selected by the parameter sweep.
- A future upgrade is to train an XGB meta-learner on `candidate_ledger` entries to selectively scale down weak 1H setups.

## Verified result

| Metric | Value |
|--------|-------|
| Return | 306.6% |
| Max DD | -21.8% |
| Sharpe | 1.68 |
| Trades | 306 |
| Win rate | 55.2% |

See `REPORT.md` for the full backtest and comparison table.
