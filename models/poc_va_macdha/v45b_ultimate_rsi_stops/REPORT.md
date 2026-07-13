# v45b_ultimate_rsi_stops Sweep Report

Generated: 2026-07-13T23:51:01.143766+00:00
Cash: $1,000 | Source: local | Window: 2024-08-01 → 2026-07-11
Universe: TSLA.US, MU.US, SPY.US, IONQ.US, APLD.US, XLP.US, QQQ.US

## Interpretation of the rule

- The LuxAlgo Ultimate RSI line is **red** when `arsi < os_value` (oversold).
- It is **green** when `arsi > ob_value` (overbought).
- This model goes **long** when the line crosses into red and **exits** when it crosses into green.

## Best by total return

- **Tag:** `tf_4h`
- **Total return:** 876.1%
- **Max drawdown:** -25.5%
- **Sharpe:** 2.02
- **Trades:** 34 | Win rate: 47%
- **Final value:** $9,761

## Best by risk-adjusted return (return / |drawdown|)

- **Tag:** `tf_4h`
- **Total return:** 876.1%
- **Max drawdown:** -25.5%
- **Sharpe:** 2.02
- **Trades:** 34 | Win rate: 47%
- **Final value:** $9,761

## Top 10 by total return

| Rank | Tag | Return | DD | Sharpe | Trades | WR | Final |
|------|-----|--------|----|--------|--------|----|-------|
| 1 | `tf_4h` | 876.1% | -25.5% | 2.02 | 34 | 47% | $9,761 |
| 2 | `tf_4h_len21_sm14_ob70_os30_RMA_EMA_atr2_5_trailTrue_reg0` | 876.1% | -25.5% | 2.02 | 34 | 47% | $9,761 |
| 3 | `tf_4h_len21_sm14_ob70_os30_RMA_EMA_atr3_0_trailTrue_reg0` | 566.4% | -28.5% | 1.74 | 34 | 53% | $6,664 |
| 4 | `tf_4h_len21_sm14_ob70_os30_RMA_EMA_atr2_75_trailTrue_reg0` | 554.6% | -28.5% | 1.74 | 32 | 50% | $6,546 |
| 5 | `tf_4h_len21_sm14_ob70_os30_RMA_EMA_atr2_25_trailTrue_reg0` | 551.3% | -31.3% | 1.75 | 32 | 56% | $6,513 |
| 6 | `tf_4h_len21_sm14_ob70_os30_RMA_EMA_atr2_25_trailFalse_reg0` | 496.6% | -33.3% | 1.67 | 33 | 52% | $5,966 |
| 7 | `tf_4h_len21_sm14_ob70_os30_RMA_EMA_atr2_0_trailTrue_reg0` | 474.0% | -37.2% | 1.70 | 40 | 55% | $5,740 |
| 8 | `tf_4h_len21_sm14_ob70_os30_RMA_EMA_atr2_75_trailFalse_reg0` | 429.2% | -41.3% | 1.59 | 34 | 47% | $5,292 |
| 9 | `tf_4h_len21_sm14_ob70_os30_RMA_EMA_atr2_0_trailFalse_reg0` | 413.7% | -40.2% | 1.55 | 27 | 63% | $5,137 |
| 10 | `tf_4h_len21_sm14_ob70_os30_RMA_EMA_atr2_5_trailFalse_reg0` | 337.9% | -36.2% | 1.47 | 36 | 44% | $4,379 |

## Top 10 by risk-adjusted

| Rank | Tag | Return | DD | Sharpe | Trades | WR | Final |
|------|-----|--------|----|--------|--------|----|-------|
| 1 | `tf_4h` | 876.1% | -25.5% | 2.02 | 34 | 47% | $9,761 |
| 2 | `tf_4h_len21_sm14_ob70_os30_RMA_EMA_atr2_5_trailTrue_reg0` | 876.1% | -25.5% | 2.02 | 34 | 47% | $9,761 |
| 3 | `tf_4h_len21_sm14_ob70_os30_RMA_EMA_atr3_0_trailTrue_reg0` | 566.4% | -28.5% | 1.74 | 34 | 53% | $6,664 |
| 4 | `tf_4h_len21_sm14_ob70_os30_RMA_EMA_atr2_75_trailTrue_reg0` | 554.6% | -28.5% | 1.74 | 32 | 50% | $6,546 |
| 5 | `tf_4h_len21_sm14_ob70_os30_RMA_EMA_atr2_25_trailTrue_reg0` | 551.3% | -31.3% | 1.75 | 32 | 56% | $6,513 |
| 6 | `tf_4h_len21_sm14_ob70_os30_RMA_EMA_atr2_25_trailFalse_reg0` | 496.6% | -33.3% | 1.67 | 33 | 52% | $5,966 |
| 7 | `tf_4h_len21_sm14_ob70_os30_RMA_EMA_atr2_0_trailTrue_reg0` | 474.0% | -37.2% | 1.70 | 40 | 55% | $5,740 |
| 8 | `tf_4h_len21_sm14_ob70_os30_RMA_EMA_atr2_75_trailFalse_reg0` | 429.2% | -41.3% | 1.59 | 34 | 47% | $5,292 |
| 9 | `tf_4h_len21_sm14_ob70_os30_RMA_EMA_atr2_0_trailFalse_reg0` | 413.7% | -40.2% | 1.55 | 27 | 63% | $5,137 |
| 10 | `tf_4h_len21_sm14_ob70_os30_RMA_EMA_atr2_5_trailFalse_reg0` | 337.9% | -36.2% | 1.47 | 36 | 44% | $4,379 |

## Errors

None.


## Suggested next improvements

1. Add a trailing ATR stop once in profit; mean-reversion can turn into a trend move against the position.
2. Use the Ultimate RSI **signal line** for confirmation: e.g., require `arsi` to cross back above its signal line before exiting, or use signal-line crossovers for entry.
3. Add a volume confirmation: only enter red if volume is expanding or above its average.
4. Add a regime filter: avoid long-only entries in strong downtrends (e.g., price below a long-period SMA).
5. Consider a short leg: sell short when the line becomes green (overbought) and cover when it becomes red.
6. Use adaptive thresholds: widen ob/os in high-volatility periods (e.g., ATR-based bands).
7. Walk-forward test: reserve the most recent 6 months for OOS validation instead of optimizing on the whole window.
