# Backtest Run Card

Generated: 2026-07-11T17:45:12.028073Z
Run directory: `/Users/syriljacob/Desktop/TradingAlgoWork/runs/poc_va_regime`

## Backtest Summary
- codes: ['TSLA.US', 'ARM.US', 'MU.US', 'SPY.US', 'IONQ.US', 'APLD.US', 'QQQ.US']
- start_date: 2024-08-01
- end_date: 2026-07-11
- interval: 1H
- engine: daily
- initial_cash: 1000000
- source: yfinance

## Reproducibility
- config_hash: `aed02da63160f55f1fe63f0f858561f68cd034de767d2e3eec2da5bf9fcf770a`
- strategy_hash: `3d06ecf49648c42f2664164e4f8b0ca8b38af6fa1c9d91019aa7cf4b4177156b`

## Data Sources
- yfinance

## Metrics
- final_value: 2173166.4620733177
- total_return: 1.1731664620733175
- annual_return: 0.4990723799325847
- max_drawdown: -0.17516020790663947
- sharpe: 1.778859482831906
- calmar: 2.8492
- sortino: 1.328
- win_rate: 0.6385542168674698
- profit_loss_ratio: 2.0575
- profit_factor: 3.6348
- max_consecutive_loss: 3
- avg_holding_days: 7.7
- trade_count: 83
- benchmark_return: 3.485542
- excess_return: -2.312376
- information_ratio: -0.9395

## Validation
- monte_carlo: {'actual_sharpe': 5.1988, 'actual_max_dd': -0.1489, 'p_value_sharpe': 0.89, 'p_value_max_dd': 0.982, 'simulated_sharpe_mean': 5.5803, 'simulated_sharpe_std': 0.3252, 'simulated_sharpe_p5': 5.0378, 'simulated_sharpe_p95': 6.119, 'n_simulations': 1000, 'n_trades': 83}

## Artifacts
- `artifacts/REGIME_PROOF.json` (38014 bytes, sha256 `9437c7cb40754cc9b46cb6d3267065a3b6128005475412ccd9f314140fb01903`)
- `artifacts/backtest_log.txt` (5468 bytes, sha256 `a70fcb72e1f8c25419765e70f0ed729e57871ded15530f7ff28e51ca52cda144`)
- `artifacts/equity.csv` (357524 bytes, sha256 `a143bb4e5861290baaebfbeb4505f19a3a0aec208027bf8b2b30b93d03e8f8d3`)
- `artifacts/metrics.csv` (392 bytes, sha256 `356a4df05a929a9433a092597e13f12a5535128f6c30b58bbe670d6c50da8702`)
- `artifacts/ohlcv_APLD.US.csv` (334326 bytes, sha256 `18bbdb31c157df97d98821d423e8dbc8b15d3f449bf4b59ff3cec9f13df2e6ff`)
- `artifacts/ohlcv_ARM.US.csv` (332296 bytes, sha256 `0d62e1e5a5ff8decd4eb902639c9848b60b199ef8d53c4329c3f9b2f0962bc14`)
- `artifacts/ohlcv_IONQ.US.csv` (340563 bytes, sha256 `752bff78443c724ad2aec84994c150df66690ba7a42eb97e5f4cded51c3d4fcf`)
- `artifacts/ohlcv_MU.US.csv` (332670 bytes, sha256 `5900c4a64c6af4f1f975bcd9840aeda517454428594f2a04f4903fe9fd23dc22`)
- `artifacts/ohlcv_QQQ.US.csv` (329756 bytes, sha256 `f48983c0371f565a273a628e3e3a25c2349f5548743d628cac8f01d123e7475a`)
- `artifacts/ohlcv_SPY.US.csv` (328018 bytes, sha256 `bd540fe5bf6d3f5c040b1bb4e191c3ae18f0f5d2fe4bd9f225e45f36b99e9801`)
- `artifacts/ohlcv_TSLA.US.csv` (333607 bytes, sha256 `fabdff03d04b583010008822d51b83b3f90d38abc636ed7738f33a0060ea7bf2`)
- `artifacts/positions.csv` (169204 bytes, sha256 `426d7ab6098551c2f78e84672b77dc6560282190a7488abcaeea7e2557f9217b`)
- `artifacts/regime_daily.csv` (43123 bytes, sha256 `540dd176e958304fe41bc04537923b0320264a715c82ac7621190d70499619e2`)
- `artifacts/trades.csv` (10042 bytes, sha256 `73bad87e699e2ff26c4bc58b4d8332b5b58910b4d00fd30ef68a4a3991263676`)
- `artifacts/trades_with_regime_v13_specialists.csv` (30545 bytes, sha256 `bcdd90801586242eafb9947370bafd655825264771c5b565702839631ff7c4d0`)
- `artifacts/trades_with_regime_v14_risk_kelly.csv` (33592 bytes, sha256 `1a3f9d97d70f3f6b4b0087ed0f747ae77119173d7b53f3b3f6239b0c351398b5`)
- `artifacts/validation.json` (331 bytes, sha256 `938f1d9105f1251a4297bf16e73a50aac1d3501a892d251d75232293bde8eab1`)
- `code/signal_engine.py` (27094 bytes, sha256 `3d06ecf49648c42f2664164e4f8b0ca8b38af6fa1c9d91019aa7cf4b4177156b`)
- `config.json` (1012 bytes, sha256 `aed02da63160f55f1fe63f0f858561f68cd034de767d2e3eec2da5bf9fcf770a`)
