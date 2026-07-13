# v45_ultimate_rsi Sweep Report

Generated: 2026-07-13T23:21:38.441578+00:00
Cash: $1,000 | Source: local | Window: 2024-08-01 → 2026-07-11
Universe: TSLA.US, MU.US, SPY.US, IONQ.US, APLD.US, XLP.US, QQQ.US

## Interpretation of the rule

- The LuxAlgo Ultimate RSI line is **red** when `arsi < os_value` (oversold).
- It is **green** when `arsi > ob_value` (overbought).
- This model goes **long** when the line crosses into red and **exits** when it crosses into green.

## Best by total return

- **Tag:** `ultimate_rsi__tf_4h_len14_sm14_ob70_os30_RMA_EMA`
- **Total return:** 255.6%
- **Max drawdown:** -59.3%
- **Sharpe:** 1.16
- **Trades:** 25 | Win rate: 80%
- **Final value:** $3,556

## Best by risk-adjusted return (return / |drawdown|)

- **Tag:** `ultimate_rsi__tf_4h_len21_sm14_ob70_os30_RMA_EMA`
- **Total return:** 230.8%
- **Max drawdown:** -41.1%
- **Sharpe:** 1.28
- **Trades:** 26 | Win rate: 69%
- **Final value:** $3,308

## Top 10 by total return

| Rank | Tag | Return | DD | Sharpe | Trades | WR | Final |
|------|-----|--------|----|--------|--------|----|-------|
| 1 | `ultimate_rsi__tf_4h_len14_sm14_ob70_os30_RMA_EMA` | 255.6% | -59.3% | 1.16 | 25 | 80% | $3,556 |
| 2 | `ultimate_rsi__tf_4h_len14_sm14_ob70_os30_RMA_SMA` | 255.6% | -59.3% | 1.16 | 25 | 80% | $3,556 |
| 3 | `ultimate_rsi__tf_4h_len14_sm21_ob70_os30_RMA_EMA` | 255.6% | -59.3% | 1.16 | 25 | 80% | $3,556 |
| 4 | `ultimate_rsi__tf_4h_len14_sm21_ob70_os30_RMA_SMA` | 255.6% | -59.3% | 1.16 | 25 | 80% | $3,556 |
| 5 | `ultimate_rsi__tf_4h_len21_sm14_ob70_os30_RMA_EMA` | 230.8% | -41.1% | 1.28 | 26 | 69% | $3,308 |
| 6 | `ultimate_rsi__tf_4h_len21_sm14_ob70_os30_RMA_SMA` | 230.8% | -41.1% | 1.28 | 26 | 69% | $3,308 |
| 7 | `ultimate_rsi__tf_4h_len21_sm21_ob70_os30_RMA_EMA` | 230.8% | -41.1% | 1.28 | 26 | 69% | $3,308 |
| 8 | `ultimate_rsi__tf_4h_len21_sm21_ob70_os30_RMA_SMA` | 230.8% | -41.1% | 1.28 | 26 | 69% | $3,308 |
| 9 | `ultimate_rsi__tf_4h_len21_sm14_ob80_os20_RMA_EMA` | 217.8% | -41.7% | 1.21 | 14 | 86% | $3,178 |
| 10 | `ultimate_rsi__tf_4h_len21_sm14_ob80_os20_RMA_SMA` | 217.8% | -41.7% | 1.21 | 14 | 86% | $3,178 |

## Top 10 by risk-adjusted

| Rank | Tag | Return | DD | Sharpe | Trades | WR | Final |
|------|-----|--------|----|--------|--------|----|-------|
| 1 | `ultimate_rsi__tf_4h_len21_sm14_ob70_os30_RMA_EMA` | 230.8% | -41.1% | 1.28 | 26 | 69% | $3,308 |
| 2 | `ultimate_rsi__tf_4h_len21_sm14_ob70_os30_RMA_SMA` | 230.8% | -41.1% | 1.28 | 26 | 69% | $3,308 |
| 3 | `ultimate_rsi__tf_4h_len21_sm21_ob70_os30_RMA_EMA` | 230.8% | -41.1% | 1.28 | 26 | 69% | $3,308 |
| 4 | `ultimate_rsi__tf_4h_len21_sm21_ob70_os30_RMA_SMA` | 230.8% | -41.1% | 1.28 | 26 | 69% | $3,308 |
| 5 | `ultimate_rsi__tf_4h_len21_sm14_ob80_os20_RMA_EMA` | 217.8% | -41.7% | 1.21 | 14 | 86% | $3,178 |
| 6 | `ultimate_rsi__tf_4h_len21_sm14_ob80_os20_RMA_SMA` | 217.8% | -41.7% | 1.21 | 14 | 86% | $3,178 |
| 7 | `ultimate_rsi__tf_4h_len21_sm21_ob80_os20_RMA_EMA` | 217.8% | -41.7% | 1.21 | 14 | 86% | $3,178 |
| 8 | `ultimate_rsi__tf_4h_len21_sm21_ob80_os20_RMA_SMA` | 217.8% | -41.7% | 1.21 | 14 | 86% | $3,178 |
| 9 | `ultimate_rsi__tf_4h` | 185.5% | -39.2% | 1.10 | 17 | 71% | $2,855 |
| 10 | `ultimate_rsi__tf_4h_len14_sm14_ob80_os20_RMA_EMA` | 185.5% | -39.2% | 1.10 | 17 | 71% | $2,855 |

## Errors

None.

## Comparison with current champion

Run on the same winner bag ($1,000, `source=local`, `interval=1H`, `2024-08-01` → `2026-07-11`):

| Model | Return | Max DD | Sharpe | Trades | WR |
|-------|--------|--------|--------|--------|----|
| v45_ultimate_rsi (best return) | 255.6% | -59.3% | 1.16 | 25 | 80% |
| v45_ultimate_rsi (best risk-adj) | 230.8% | -41.1% | 1.28 | 26 | 69% |
| v39b_live_adapt (champion baseline) | 309.7% | -13.1% | 2.70 | 141 | 69% |
| v39d_confluence (champion baseline) | 357.5% | -13.4% | 2.82 | 135 | 67% |

The Ultimate RSI color rule is profitable but not yet competitive with the champion. It produces a higher win rate and fewer trades, but the drawdown is much larger because the mean-reversion entries have no protective stop. The next improvements below focus on cutting those drawdowns.

## Suggested next improvements

1. Add a trailing ATR stop once in profit; mean-reversion can turn into a trend move against the position.
2. Use the Ultimate RSI **signal line** for confirmation: e.g., require `arsi` to cross back above its signal line before exiting, or use signal-line crossovers for entry.
3. Add a volume confirmation: only enter red if volume is expanding or above its average.
4. Add a regime filter: avoid long-only entries in strong downtrends (e.g., price below a long-period SMA).
5. Consider a short leg: sell short when the line becomes green (overbought) and cover when it becomes red.
6. Use adaptive thresholds: widen ob/os in high-volatility periods (e.g., ATR-based bands).
7. Walk-forward test: reserve the most recent 6 months for OOS validation instead of optimizing on the whole window.
