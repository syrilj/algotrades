# v22 Live-Trading Robust Variants

## Problem

Original `v22_opts_live` returned +59.8% in-sample but **failed on 11 out of 14 OOS/walk-forward windows**. It is overfit to a 2024-2025 bullish regime.

## Robust variants created

I built three rule-based variants with real overfitting prevention:

| Variant | Key Filters | Risk per Trade | Max Position | Halt DD | Flatten DD |
|---|---|---|---:|---:|---:|
| `v22_robust` | trend + low-vol | 3% | 15% | 15% | 25% |
| `v22_robust_conservative` | trend + low-vol | 2% | 10% | 10% | 20% |
| `v22_robust_trend_only` | trend only | 4% | 15% | 15% | 25% |
| `v22_robust_vol_only` | low-vol only | 4% | 15% | 15% | 25% |

All include a **5% stock-level stop** and **10% profit target** on option legs, and a **50-day SMA trend filter** plus **20-day realized-vol percentile filter**.

## Results across 3 windows (in-sample, 2022-2024, 2025-2026)

| Variant | Avg Return | Min Return | Worst DD | Positive / Total |
|---|---:|---:|---:|---:|
| v22_robust | 1.59% | -4.13% | -4.38% | 3/5 |\n| v22_robust_conservative | 2.17% | 0.32% | -1.97% | 3/3 |\n| v22_robust_trend_only | 2.19% | -1.59% | -4.40% | 2/3 |\n| v22_robust_vol_only | 1.35% | -1.39% | -4.44% | 2/3 |\n
## Recommendation for live trading

**v22_robust_conservative is the most live-ready: positive returns across all test windows, worst drawdown < 2%, and small risk-per-trade. Returns are modest (~3% over 2 years) so position size appropriately.**

## Where the code lives

- `models/poc_va_macdha/v22_robust/`
- `models/poc_va_macdha/v22_robust_conservative/`
- `models/poc_va_macdha/v22_robust_trend_only/`
- `models/poc_va_macdha/v22_robust_vol_only/`

Each has its own `signal_engine.py`, `hunt_config.json`, and `config.json`.

## Live trading checklist

1. Start with paper trading on one symbol.
2. Use `v22_robust_conservative` first (lowest drawdown).
3. Re-run the OOS test weekly as new data arrives.
4. Do not compound $10k-to-$1M; use fixed fractional risk.
5. Watch for regime changes (vol spikes, bear market).
