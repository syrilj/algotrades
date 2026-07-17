## 2026-07-16T17:37:18-06:00
Objective: Implement the v83_adaptive_regime SignalEngine (Milestone 2).

Tasks:
1. Update `models/poc_va_macdha/v83_adaptive_regime/signal_engine.py` to implement the regime-aware sleeve routing logic.
   - Use point-in-time microstructure features from `tools/institutional_flow/features.py` by inserting the `tools` directory into `sys.path` and calling `compute_features(df)`.
   - Implement safe fallbacks: if required columns ('open', 'high', 'low', 'close', 'volume') are missing, default `core_regime_scale` to 1.0.
   - Implement the following regime-routing parameters in the SignalEngine (and load them from `hunt_config.json` overrides):
     - `core_trend_low_vol_scale`: default 1.0
     - `core_trend_high_vol_scale`: default 0.60
     - `core_chop_low_vol_scale`: default 0.30
     - `core_chop_high_vol_scale`: default 0.00
     - `enable_rsi_vol_gate`: default True
     - `core_rsi_ob_filter`: default 70.0
     - `core_rsi_os_filter`: default 30.0
   - Dynamically scale the core signal (`co_adj = co * core_regime_scale`) before determining active sleeves (`core_on = co_adj > 1e-9`). Use `co_adj` in all weight, confidence, and sleeve ID calculations.
2. Verify that `models/poc_va_macdha/v83_adaptive_regime/hunt_config.json` contains these default parameters.
3. Update the mock test `test_v83_generate_format_mocked` in `tests/test_v83_e2e.py` to include the required OHLCV columns ('open', 'high', 'low', 'volume', 'close') in the dummy dataframe so it passes the new engine format requirements.
4. Run `pytest tests/test_v83_e2e.py` to verify that the E2E tests pass.
