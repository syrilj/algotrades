# Backtest Run Card

Generated: 2026-07-11T17:51:47.244785Z
Run directory: `/Users/syriljacob/Desktop/TradingAlgoWork/runs/poc_va_v13_long`

## Backtest Summary
- codes: ['TSLA.US', 'ARM.US', 'MU.US', 'SPY.US', 'IONQ.US', 'APLD.US']
- start_date: 2020-01-01
- end_date: 2026-07-11
- interval: 1D
- engine: daily
- initial_cash: 1000000
- source: yfinance

## Reproducibility
- config_hash: `2a9f2d86b10697a21b4e425a206829d32f7c8e4de48e2896768b0c468773458d`
- strategy_hash: `53da0d9a31f5950d52908db66adbb97036911d811090cd3006f59f9e80fc1ade`

## Data Sources
- yfinance

## Metrics
- final_value: 1695935.3908432226
- total_return: 0.6959353908432226
- annual_return: 0.08466028563909611
- max_drawdown: -0.3601052535102024
- sharpe: 0.446065723662057
- calmar: 0.2351
- sortino: 0.4187
- win_rate: 0.504950495049505
- profit_loss_ratio: 1.2143
- profit_factor: 1.2386
- max_consecutive_loss: 7
- avg_holding_days: 3.8
- trade_count: 202
- benchmark_return: 16.752364
- excess_return: -16.056429
- information_ratio: -1.0038

## Validation
- Not present.

## Artifacts
- `artifacts/equity.csv` (165484 bytes, sha256 `a48c9002f2ff7ead71d4366e2d7011a3b63c89b7d368ea57add8a0f5a06156e6`)
- `artifacts/metrics.csv` (395 bytes, sha256 `276bc844ce7ff93fb4be3685e35b1f6e64ee60cde52c7651659b09196dce311e`)
- `artifacts/ohlcv_APLD.US.csv` (97235 bytes, sha256 `d38d26897fffed2889fdde91fde024b980dff58bb00aedbd90889ecc50312fe6`)
- `artifacts/ohlcv_ARM.US.csv` (62796 bytes, sha256 `4de442d7d6d697af966e528429de512c62c807f94dea807c26f85467e955fc83`)
- `artifacts/ohlcv_IONQ.US.csv` (126178 bytes, sha256 `11b73be0da2f18eedda94ef446bd1e10f352d1e969baf88bcadf7503e4d73c27`)
- `artifacts/ohlcv_MU.US.csv` (145896 bytes, sha256 `2917b78eba2f57da11bdde1cc58328e1e335e5096cc015220e796f031dcba6c5`)
- `artifacts/ohlcv_SPY.US.csv` (147868 bytes, sha256 `34a3d3284e1965498bbf43d8cb31e6ca84021e3bacb16ce14e5eb534eaca5b79`)
- `artifacts/ohlcv_TSLA.US.csv` (148059 bytes, sha256 `2acebce1ac79a1d934f4c754a10c5bf47ef22b3f6945eef375d0fa8efb9aef0a`)
- `artifacts/positions.csv` (58464 bytes, sha256 `bf9fdabc93ffb55af2c3f4708618e010348d812ee06dad1c58280e9c2d31643c`)
- `artifacts/trades.csv` (24291 bytes, sha256 `4b02b10c8bb5890f5b170c8f36d8dbec2e335eeb32c4c62eb6e679dfcd73caa0`)
- `code/signal_engine.py` (20185 bytes, sha256 `53da0d9a31f5950d52908db66adbb97036911d811090cd3006f59f9e80fc1ade`)
- `config.json` (1020 bytes, sha256 `2a9f2d86b10697a21b4e425a206829d32f7c8e4de48e2896768b0c468773458d`)

## Phase A note
- Frozen v13 routing/filters; no ML.
- Yahoo blocked 1H before ~2024-07-12 → ran **1D** from 2020-01-01.
- **FAIL** vs bar (PF>1.2, DD<25%, Sharpe>0.5): PF 1.24 ✓, DD −36% ✗, Sharpe 0.45 ✗.
- Report: `models/poc_va_macdha/v13_long_oos/OOS_REPORT.md`
