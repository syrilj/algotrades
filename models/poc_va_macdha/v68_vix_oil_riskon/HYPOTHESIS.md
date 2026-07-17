# v68_vix_oil_riskon

## Thesis

High-beta names (IONQ, APLD, TSLA, MU, …) work best as **risk-on beta** when
the macro backdrop says fear and inflation stress are easing:

1. **VIX declining** — volatility crushing / fear leaving the market
2. **Oil (USO) declining** — inflation / geopolitical stress easing

Together this is a classic setup for an **SPY rebound**, which high-beta
names amplify. Entering high-beta *without* this confirmation is where a lot
of the drawdown lives.

## Design

- Base engine: frozen `v39d_confluence`
- **Hard entry gate** on high-beta only: new longs require risk-on over
  `lookback_days` (default 5 trading days), measured on daily closes with
  t−1 lag (causal).
- `combine`: `"or"` (default, yield-positive) or `"and"` (stricter, fewer trades).
  - OR: VIX↓ *or* oil↓
  - AND: VIX↓ *and* oil↓
- Non-high-beta (SPY, QQQ, XLP, …): pass through base signals unchanged.
- Existing positions exit when the base engine exits (gate is entry-only).
- Optional soft mode (`gate_mode=soft`) sizes high-beta entries to
  `soft_size` instead of zero when the gate fails.

## Empirics (2024-08-01 → 2026-07-11, $1k, local 1H)

| setup | IONQ ret | IONQ DD | IONQ Sharpe | high-beta ret | high-beta DD | high-beta Sharpe |
|-------|----------|---------|-------------|---------------|--------------|------------------|
| v39d baseline | +120% | -20.0% | 1.58 | +400% | -13.1% | 2.77 |
| hard AND | +33% | -5.9% | 1.52 | +94% | -7.9% | 2.16 |
| **hard OR (default)** | **+132.5%** | **-16.4%** | **1.79** | **+403%** | **-10.0%** | **2.95** |

AND maximizes precision; OR is the form that improves yield.

## Data

- VIX: `data_cache/1d/VIX.parquet`
- Oil proxy: `data_cache/1d/USO.parquet` (USO ETF; crude beta without futures
  roll handling)

## Success criteria

Beat `v39d_confluence` on the same universe on **return and/or max DD and
Sharpe**, with enough trades to not be a one-trade fluke (n ≥ 15 preferred).
