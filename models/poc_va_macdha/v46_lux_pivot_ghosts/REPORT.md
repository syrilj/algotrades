# v46_lux_pivot_ghosts Sweep Report

Generated: 2026-07-14
Cash: $1,000 (equity) | $10,000 (screen) | Window: 2024-08-01 → 2026-07-11
Equity Universe: TSLA.US, MU.US, SPY.US, IONQ.US, APLD.US, XLP.US, QQQ.US
Screen Universe: NVDA.US, AVGO.US, TSLA.US, JPM.US, XOM.US, UNH.US, HOOD.US, SPY.US, QQQ.US

## Interpretation of the rule

The LuxAlgo "Pivot Points High Low & Missed Reversal Levels" indicator detects confirmed pivot highs and lows. Two execution modes are now implemented:

- `zigzag` (default): long when a pivot low is confirmed, flat when a pivot high is confirmed.
- `missed_sr`: only enter long when a pivot low is a **higher low** (close above the new swing low) and exit when a pivot high is a **lower high** or the close falls below the previous swing-low support.

## Zig-zag baseline

The default `zigzag` mode with `pivot_length=10` on the native 1H frame is the best practical standalone result.

| Tag | Return | DD | Sharpe | Trades | WR | Final |
|-----|--------|----|--------|--------|----|-------|
| `p10_1h` | **443.1%** | **-27.1%** | **2.01** | **532** | 42% | **$5,431** |
| `p50_2h` | 419.8% | -42.7% | 1.78 | 54 | 54% | $5,198 |
| `p10_1D` | 315.0% | -46.9% | 1.55 | 70 | 54% | $4,150 |
| `p20_4h` | 272.5% | -47.3% | 1.47 | 68 | 52% | $3,725 |

`p50_1D` produced a 997.1% return with only **3 trades**, so it is treated as an outlier and not considered robust.

## Missed-level S/R confirmation

`strategy_mode=missed_sr` was added to test the hypothesis that the LuxAlgo "missed" reversal levels provide a stronger support/resistance confirmation filter.

| Tag | Return | DD | Sharpe | Trades | WR | Final |
|-----|--------|----|--------|--------|----|-------|
| `missed_sr_p20_1D` | 457.8% | -59.0% | 1.46 | 6 | 33% | $5,578 |
| `missed_sr_p10_2h` | **201.6%** | **-25.4%** | **1.50** | **38** | 50% | **$3,016** |
| `missed_sr_p50_1h` | 101.7% | -39.5% | 0.98 | 20 | 60% | $2,017 |
| `missed_sr_p20_1h` | 46.7% | -31.9% | 0.69 | 30 | 43% | $1,467 |
| `missed_sr_p10_1D` | 38.2% | -31.5% | 0.70 | 9 | 67% | $1,382 |

The `missed_sr` filter improves the `p10_2h` risk profile versus `zigzag` `p10_2h` (124.6% / -45.3% / Sharpe 1.20 → 201.6% / -25.4% / Sharpe 1.50), but it degrades the best 1H configuration and does not reach the champion level.

## Screen bag results (source: yfinance, 1D, $10k)

Zig-zag mode:

| Rank | Tag | Return | DD | Sharpe | Trades | WR | Final |
|------|-----|--------|----|--------|--------|----|-------|
| 1 | `screen_p10` | 75.1% | -24.5% | 1.32 | 90 | 51% | $17,513 |
| 2 | `screen_p50` | 11.0% | -20.7% | 0.40 | 12 | 92% | $11,099 |
| 3 | `screen_p20` | -7.6% | -31.8% | -0.06 | 44 | 48% | $9,243 |

Missed-level S/R mode:

| Rank | Tag | Return | DD | Sharpe | Trades | WR | Final |
|------|-----|--------|----|--------|--------|----|-------|
| 1 | `screen_miss_sr_p50` | 18.7% | -38.1% | 0.46 | 2 | 100% | $11,866 |
| 2 | `screen_miss_sr_p10` | -9.0% | -34.9% | -0.04 | 14 | 43% | $9,101 |
| 3 | `screen_miss_sr_p20` | -35.3% | -57.1% | -0.22 | 6 | 17% | $6,472 |

The `missed_sr` filter is **not** the missing link on the broad screen bag; it reduces trade count and returns versus the simple `zigzag` read.

## Comparison with champions

| Model | Return | Max DD | Sharpe | Trades | WR |
|-------|--------|--------|--------|--------|-----|
| `v46_lux_pivot_ghosts` zigzag `p10_1h` | 443.1% | -27.1% | 2.01 | 532 | 42% |
| `v46_lux_pivot_ghosts` missed_sr `p10_2h` | 201.6% | -25.4% | 1.50 | 38 | 50% |
| `v45b_ultimate_rsi_stops` | 876.1% | -25.5% | 2.02 | 34 | 47% |
| `v39d_confluence` | 357.5% | -13.4% | 2.82 | 135 | 67% |

## Verdict

- **Can it outperform?** Not as a standalone refinement. The `missed_sr` filter improves the `p10_2h` risk profile (201.6% / -25.4% / Sharpe 1.50) versus the `p10_2h` zigzag, but it still trails `v45b` and `v39d` on risk-adjusted return.
- The best `v46` result remains the **zigzag `p10_1h`** run: 443.1% return, -27.1% drawdown, Sharpe 2.01. This is competitive on return and Sharpe, but the drawdown is double `v39d`'s and slightly worse than `v45b`'s.
- The `missed_sr` filter is too restrictive on the broad daily screen (returns collapse to -9% and -35% for `p10` and `p20`), indicating the missed-level confirmation does not generalize well across slower timeframes or broader universes.
- **Conclusion:** the LuxAlgo pivot/ghost logic is a valid structural trend signal, but the missed-level S/R confirmation is **not the missing link** for a champion standalone long-only model. It is best kept as an optional signal mode for slower, lower-frequency swing trading, or as a secondary filter inside an ensemble.

## Suggested next improvements

1. Add a regime filter: avoid long-only entries when price is below a long-period SMA (e.g., 200-period).
2. Use the `missed_sr` signal as a **secondary filter** for `v39d`/`v45b` entries rather than a standalone trigger.
3. Walk-forward test the `p10_1h` zigzag and `p10_2h` missed_sr configs on a 6-month OOS window to verify robustness.
4. Combine the LuxAlgo pivot model with a different primary signal (e.g., trend strength or volatility compression) to reduce late entries in choppy 1H data.
5. Add a short leg to capture the missed-level reversal when a lower high is confirmed with bearish follow-through.

## Errors

None.
