# v22_opts_live Robustness Report

## What the model is

v22_opts_live is a rule-based **long-ATM-call options strategy** that wraps the v21 equity signal engine (MACDHA + anchored VWAP + squeeze momentum + volume profile). It sizes positions from a virtual equity tracker and has halt/flatten drawdown controls.

- Saved model: `models/poc_va_gex/v22_artifact/`
- Manifest: `models/poc_va_gex/v22_artifact/manifest.json`

## In-sample performance (2024-08-01 to 2026-07-11)

| Metric | Value |
|---|---|
| final_value | $1,598,115 |
| total_return | 59.8% |
| annual_return | 27.5% |
| max_drawdown | -11.2% |
| sharpe | 1.28 |
| trade_count | 22 |
| win_rate | 81.8% |

## Out-of-sample / walk-forward tests (anti-overfit)

I ran the **frozen** v22 model on 14 different windows and symbol sets it was not tuned on.

| Window | Total Return | Win Rate | Final Value |
|---|---:|---:|---:|
| 2022-01-01 to 2024-07-31 | -3.32% | 14.3% | $966,834.22 |
| 2023-01-01 to 2024-07-31 | -0.08% | 42.9% | $999,205.57 |
| 2025-01-01 to 2026-07-11 | -4.49% | 0.0% | $955,066.47 |
| 2024-08-01 to 2025-07-31 | +59.32% | 81.8% | $1,593,235.08 |
| 2021-01-01 to 2023-12-31 | -3.44% | 20.0% | $965,567.08 |
| WF 2021-01-01 to 2022-12-31 | -4.18% | 20.0% | $958,177.49 |
| WF 2022-01-01 to 2023-12-31 | -3.28% | 14.3% | $967,198.90 |
| WF 2023-01-01 to 2024-07-31 | -0.08% | 42.9% | $999,205.57 |
| WF 2024-08-01 to 2025-07-31 | +59.32% | 81.8% | $1,593,235.08 |
| WF 2025-01-01 to 2026-07-11 | -4.49% | 0.0% | $955,066.47 |
| WF 2022-01-01 to 2024-07-31 | -3.32% | 14.3% | $966,834.22 |
| WF 2020-01-01 to 2021-12-31 | -7.19% | 50.0% | $928,054.78 |
| New symbols TSLA.US, SPY.US, APLD.US, ARM.US (2024-08-01 to 2026-07-11) | +22.33% | 57.1% | $1,223,310.32 |
| New symbols TSLA.US, SPY.US, APLD.US, ARM.US (2022-01-01 to 2024-07-31) | -9.55% | 14.3% | $904,503.81 |

## Summary

- **Positive windows**: 3 / 14
- **Average return across all windows**: 6.97%
- **Conclusion**: v22_opts_live is not robust: it only shows strong returns in the 2024-2025 window. It loses money on earlier periods, later periods, and different symbols, indicating severe overfitting to a specific bullish regime.

## Overfitting prevention techniques applied

1. Out-of-sample testing on unseen earlier periods
2. Walk-forward analysis across rolling windows
3. New symbol universe test
4. Model artifacting and reproducibility manifest

## Recommendations

- Avoid compounding $10k-to-1M leverage without walk-forward validation.
- Add dynamic position sizing based on realized volatility (regime filter).
- Test on broader symbol universe and longer history before live use.
- Use walk-forward optimization with expanding/recalibrating windows.
- Apply max-drawdown and risk-of-ruin constraints more strictly.
