# Backtest Run Card

Generated: 2026-07-11T17:59:37.277489Z
Run directory: `/Users/syriljacob/Desktop/TradingAlgoWork/runs/poc_va_wr80`

## Backtest Summary
- codes: ['APLD.US', 'IONQ.US', 'QQQ.US']
- start_date: 2024-08-01
- end_date: 2026-07-11
- interval: 1H
- engine: daily
- initial_cash: 1000000
- source: yfinance

## Reproducibility
- config_hash: `95020d8c0530c0dff629c4118e6f4663d065718f5400a6c367b60a04a4a25713`
- strategy_hash: `a9a846b4ef6807a9d24aaedca71acb0965c06ffdf905e363e6ea092a6086a5d0`

## Data Sources
- yfinance

## Metrics
- final_value: 1711956.9012478457
- total_return: 0.7119569012478457
- annual_return: 0.32369010916713714
- max_drawdown: -0.11312622260719349
- sharpe: 1.389291882915245
- calmar: 2.8613
- sortino: 0.6505
- win_rate: 0.8333333333333334
- profit_loss_ratio: 3.9372
- profit_factor: 19.6862
- max_consecutive_loss: 1
- avg_holding_days: 12.7
- trade_count: 12
- benchmark_return: 4.928149
- excess_return: -4.216192
- information_ratio: -1.2423

## Validation
- monte_carlo: {'actual_sharpe': 13.1997, 'actual_max_dd': -0.0228, 'p_value_sharpe': 0.027, 'p_value_max_dd': 0.623, 'simulated_sharpe_mean': 11.2294, 'simulated_sharpe_std': 1.0076, 'simulated_sharpe_p5': 9.6543, 'simulated_sharpe_p95': 12.8965, 'n_simulations': 1000, 'n_trades': 12}

## Artifacts
- `artifacts/ENGINE_LOOP.json` (1912 bytes, sha256 `d5de25d2e684bf420207acd5ea02258a27c21b984791d5352dee738c97a6ea34`)
- `artifacts/FEEDBACK_LOOP.json` (3582 bytes, sha256 `084f90ca285d4634b441d6176c2f1afa94a7005cc90f99c39b14baae51404e91`)
- `artifacts/SUCCESS.json` (442 bytes, sha256 `0becfa627ff8d887cc6a38a93c96c9fabaf49f3b9267aa315e9552f3ef75e8a8`)
- `artifacts/backtest_log.txt` (4248 bytes, sha256 `95dc1a76c0f3d4746ee7194a367309485f39ae101e4f022380d83f2a9193387d`)
- `artifacts/enriched_trades.csv` (54917 bytes, sha256 `9285b53858148948df964b0bddf7fb69f7274b9db07609e637449514b4b360db`)
- `artifacts/equity.csv` (337502 bytes, sha256 `171fc8f1ad68ae3a51c0c9848a6b9497504baaeb65ea69f6685b109b7caaca69`)
- `artifacts/metrics.csv` (396 bytes, sha256 `b9b11e98a3433c62497fa2c54bdd6681d06f08e4c321aff4f1494e14de865076`)
- `artifacts/ohlcv_AAPL.US.csv` (337669 bytes, sha256 `9bc1482ac54043152d8967e935aa9441beb54ce585a6f16f114b736aef1c53d3`)
- `artifacts/ohlcv_AMZN.US.csv` (338989 bytes, sha256 `f71eefb02aa0b2bcf160c26180f31abcc78f379be6a5cf6995e0a939cabd2ea7`)
- `artifacts/ohlcv_APLD.US.csv` (334326 bytes, sha256 `18bbdb31c157df97d98821d423e8dbc8b15d3f449bf4b59ff3cec9f13df2e6ff`)
- `artifacts/ohlcv_GOOGL.US.csv` (336807 bytes, sha256 `3eff3461c42123073365954fdae820288efea2bdfe60a60efc5063f24e87fdf5`)
- `artifacts/ohlcv_IONQ.US.csv` (340563 bytes, sha256 `752bff78443c724ad2aec84994c150df66690ba7a42eb97e5f4cded51c3d4fcf`)
- `artifacts/ohlcv_META.US.csv` (320678 bytes, sha256 `b96ed9ebacad62cfbdcf53efac1b7d8c133e20ae9cb1d0de0a6d80084e6d46c7`)
- `artifacts/ohlcv_MSFT.US.csv` (330598 bytes, sha256 `d18b0e0014a5f79fa71a14807c4f614950739429ed6e0e47f6b10c2e84b103ef`)
- `artifacts/ohlcv_MU.US.csv` (332670 bytes, sha256 `5900c4a64c6af4f1f975bcd9840aeda517454428594f2a04f4903fe9fd23dc22`)
- `artifacts/ohlcv_NVDA.US.csv` (342799 bytes, sha256 `27b00906965c49b5f1d404dec376e95f28e9ed1c7e37807498e71d8fa787788b`)
- `artifacts/ohlcv_QQQ.US.csv` (329756 bytes, sha256 `f48983c0371f565a273a628e3e3a25c2349f5548743d628cac8f01d123e7475a`)
- `artifacts/ohlcv_TSLA.US.csv` (333607 bytes, sha256 `fabdff03d04b583010008822d51b83b3f90d38abc636ed7738f33a0060ea7bf2`)
- `artifacts/positions.csv` (109517 bytes, sha256 `82304fdeb5cad48420e77fb10d485acbd2cab89911deacc8d9af56cac1d55e6d`)
- `artifacts/regime.csv` (34377 bytes, sha256 `66b053d9ce79fa9e29a0f48c932ac8430efc38a94ee07c9ae9a5d87199801b6f`)
- `artifacts/round1_trades.csv` (9102 bytes, sha256 `d93b3dee0f4f2e420cb8bd15b5895cd414577e416850104b5cf590f7cfec254e`)
- `artifacts/round2_trades.csv` (9102 bytes, sha256 `d93b3dee0f4f2e420cb8bd15b5895cd414577e416850104b5cf590f7cfec254e`)
- `artifacts/round3_trades.csv` (6944 bytes, sha256 `6b27f2c07df0189a4e7ba9af7386524be17c2e0a735d7ae9ae90fb1d1017d955`)
- `artifacts/trades.csv` (1535 bytes, sha256 `e61095d7b185a02bfe740cec90f0ef26347292d1e8519db266177490c9d59c01`)
- `artifacts/validation.json` (336 bytes, sha256 `b57cab3a4883d3aeeb2feba260b43bd38106c32fcea80e061f3ce8d7ca86df03`)
- `code/signal_engine.py` (27138 bytes, sha256 `a9a846b4ef6807a9d24aaedca71acb0965c06ffdf905e363e6ea092a6086a5d0`)
- `config.json` (849 bytes, sha256 `95020d8c0530c0dff629c4118e6f4663d065718f5400a6c367b60a04a4a25713`)
