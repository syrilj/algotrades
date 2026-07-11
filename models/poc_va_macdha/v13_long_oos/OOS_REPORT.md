# v13_long_oos — Phase A OOS Report

## Verdict: **FAIL**

Frozen v13 specialists on longer history do **not** clear the Phase A pass bar. Edge looks concentrated in 2023–2024; earlier and recent years are weak — consistent with short-window sample luck rather than durable OOS flesh.

## Pass bar

| Metric | Bar | Long OOS | Check |
|--------|-----|----------|-------|
| Profit factor | > 1.2 | 1.2386 | PASS |
| Max drawdown | < 25% | -36.01% | FAIL |
| Sharpe | > 0.5 | 0.4461 | FAIL |

## vs v13 short-window baseline (1H, 2024-08-01..2026-07-11)

| Metric | v13 short | v13_long_oos (1D) | Delta |
|--------|-----------|------------------|-------|
| PF | 1.4456 | 1.2386 | -0.2070 |
| Max DD | -43.45% | -36.01% | +7.44% |
| Sharpe | 1.0805 | 0.4461 | -0.6344 |
| Win rate | 59.00% | 50.50% | -8.50% |
| Total return | 105.62% | 69.59% | -36.02% |
| Trades | 200 | 202 | |

## Data issues

- **Yahoo 1H hard limit (~730 days):** requested `2020-01-01` + `interval=1H` failed for all tickers. Effective Phase A run uses **`interval=1D`** with frozen v13 routing (no filter retune).
- See `config_1h_max.json` for max same-interval 1H window (`2024-07-12`).
- IPO / listing truncation:
  - `APLD.US`: 2022-04-13 → 2026-07-10 (1063 bars)
  - `ARM.US`: 2023-09-14 → 2026-07-10 (707 bars)
  - `IONQ.US`: 2021-01-04 → 2026-07-10 (1385 bars)
  - `MU.US`: 2020-01-02 → 2026-07-10 (1638 bars)
  - `SPY.US`: 2020-01-02 → 2026-07-10 (1638 bars)
  - `TSLA.US`: 2020-01-02 → 2026-07-10 (1638 bars)

## Yearly walk-forward slices (evaluate only; no retune)

| Year | Return | Max DD | Sharpe | PF | Win rate | Trades |
|------|--------|--------|--------|----|----------|--------|
| 2020 | -4.6% | -16.0% | -0.21 | 0.81 | 47.8% | 23 |
| 2021 | -23.2% | -25.0% | -1.00 | 0.35 | 42.9% | 28 |
| 2022 | -5.7% | -19.5% | -0.09 | 0.90 | 43.8% | 32 |
| 2023 | 76.7% | -13.3% | 2.30 | 4.36 | 51.5% | 33 |
| 2024 | 69.1% | -14.7% | 2.51 | 10.22 | 78.1% | 32 |
| 2025 | 2.9% | -36.0% | 0.25 | 1.09 | 42.9% | 35 |
| 2026 | -20.3% | -27.3% | -1.70 | 0.42 | 42.1% | 19 |

## Quarterly summary (PF by quarter)

| Quarter | Return | Max DD | PF | Trades |
|---------|--------|--------|----|--------|
| 2020Q1 | -1.9% | -4.7% | 0.18 | 4 |
| 2020Q2 | -10.6% | -15.1% | 0.33 | 9 |
| 2020Q3 | 1.0% | -4.0% | 1.14 | 7 |
| 2020Q4 | 7.9% | -3.0% | inf | 3 |
| 2021Q1 | -16.6% | -19.3% | 0.05 | 6 |
| 2021Q2 | 5.2% | -4.0% | 2.31 | 6 |
| 2021Q3 | -7.5% | -8.6% | 0.34 | 11 |
| 2021Q4 | -1.1% | -2.5% | 0.23 | 5 |
| 2022Q1 | 9.1% | -5.7% | 2.53 | 5 |
| 2022Q2 | -6.8% | -14.0% | 0.18 | 6 |
| 2022Q3 | -0.2% | -13.8% | 0.99 | 10 |
| 2022Q4 | -6.3% | -15.7% | 0.78 | 11 |
| 2023Q1 | 8.9% | -7.6% | 1.59 | 9 |
| 2023Q2 | 40.8% | -5.6% | 11.83 | 8 |
| 2023Q3 | -4.4% | -8.2% | 0.27 | 8 |
| 2023Q4 | 21.1% | -3.8% | 679.16 | 8 |
| 2024Q1 | 12.5% | -2.8% | inf | 8 |
| 2024Q2 | 6.3% | -1.5% | 17.58 | 5 |
| 2024Q3 | 5.7% | -0.7% | inf | 4 |
| 2024Q4 | 34.3% | -14.7% | 7.07 | 15 |
| 2025Q1 | -9.3% | -25.3% | 0.88 | 9 |
| 2025Q2 | -1.7% | -21.5% | 0.77 | 8 |
| 2025Q3 | -3.0% | -6.2% | 0.33 | 10 |
| 2025Q4 | 14.8% | -4.7% | 5.62 | 8 |
| 2026Q1 | -10.5% | -23.5% | 0.34 | 10 |
| 2026Q2 | -13.8% | -13.8% | 0.57 | 8 |
| 2026Q3 | 0.8% | -0.8% | inf | 1 |

## Implication

Per EDGE_RESEARCH Phase A: **If Phase A fails → edge is sample noise; stop adding ML** until primary proves OOS flesh (and/or Phase C data upgrade restores true multi-year 1H).

## Files

- `models/poc_va_macdha/v13_long_oos/results.json`
- `models/poc_va_macdha/v13_long_oos/config.json` (1D long)
- `models/poc_va_macdha/v13_long_oos/config_1h_max.json`
- `models/poc_va_macdha/v13_long_oos/config_liquid.json` (written; not required for FAIL)
- `runs/poc_va_v13_long/`
