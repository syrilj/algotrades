# Agent Notes for TradingAlgoWork

## Backtest Entry Points
- `backtest.runner.py` is the main runner. It reads `config.json` and loads `signal_engine.py`.
- `tools/dynamic_model_rank.py` (`dmr`) provides `run_one(model, mode, codes, start, end, tag, cash, force_1d)`.
- `tools/evolve/pipeline.py` / `tools/evolve/farm.py` manage multi-generation model ranking and evolution.

## Current Champion Equity Model
- `models/poc_va_macdha/v39d_confluence/` is the current best single model.
- Verified result at `$1,000` scale on `EQUITY_WINNER_BAG` (2024-08-01 to 2026-07-11, `source=local`, `interval=1H`): 357.5% return, -13.4% max drawdown, Sharpe 2.82, 135 trades, 67% win rate, final $4,575.
- Reconcile/run: `.venv/bin/python tools/baseline_manifest.py --cash 1000`.
- Legacy `source=yfinance` result (367.1% / Sharpe 2.80 / final $4,671) was on unadjusted prices and is kept as historical evidence, not the contract.
- `models/poc_va_macdha/v41_ensemble_feedback/` best `perf_weighted` variant (`v39b_live_adapt` + `v39d_confluence`, `perf_forward=1`, `perf_metric=raw_return`): 359.2% return, -13.3% max drawdown, Sharpe 2.82, 135 trades, 67% win rate.
- `EQUITY_WINNER_BAG` in `tools/evolve/farm.py` is `["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "XLP.US", "QQQ.US"]`.

## Arete Feedback Loop
- `tools/feedback_loop_arete.py` runs `v39b` baseline against `v40_arete_pro` variants.
- Usage: `.venv/bin/python tools/feedback_loop_arete.py --cash 1000` (use `--quick` for baseline + full v40 only).
- Outputs `runs/feedback_loop_arete/LEADERBOARD.md` and `STATE.json`.

## Key Findings (2026-07-12 run)
- `v40_arete_pro` (Arete overlay on `v39b`) underperforms the baseline on return.
- Best `v40` variant was `v40_ma_only` (216% vs `v39b` 310%), but with higher drawdown and lower Sharpe.
- The Arete MA/Fib/SOX gates are too restrictive for the `v39b` signal set; they reduce trade count and final return.
- No current model approaches the "$1000 to $1M" target. The best equity backtest turns $1000 into ~$4,575 in two years (v39d_confluence on source=local adjusted data).

## v42 Trend Breakout
- `models/poc_va_macdha/v42_trend_breakout/` is a new teacher model built to break the correlation plateau between `v39b` and `v39d`.
- Standalone backtest on `EQUITY_WINNER_BAG`: 7.4% return, -37.8% max drawdown, Sharpe 0.28, 161 trades — not a useful standalone teacher.
- `v42` was integrated into the `v41_ensemble_feedback` sweep; every tested combination with `v42` underperforms the `v39b+v39d` baseline.
- Conclusion: `v42_trend_breakout` is not selected for the current ensemble; keep it as a research artifact for future signal decomposition.

## v44 Absorption (OrderFlow / Delta / Wick)
- `models/poc_va_macdha/v44_absorption/` adds an OHLCV-safe `order_flow_state` sensor (candle-delta proxy, wick absorption, volume/delta clusters, CVD bias, composite flow score) to `v39d_confluence`.
- Usage: `.venv/bin/python tools/train_v44_meta.py --seed --retrain`.
- Final backtest on `EQUITY_WINNER_BAG` ($1,000, source=local, 1H): +262.7% return, -17.8% max drawdown, Sharpe 2.24, 158 trades, final $3,627.
- This underperforms both `v39b_live_adapt` (+309.7% / -13.1% / Sharpe 2.70) and `v39d_confluence` (+357.5% / -13.4% / Sharpe 2.82).
- Conclusion: `v44_absorption` is not promoted; keep as a research artifact. The OHLCV approximation is too noisy and the retrained XGB does not match the original v39d model's selection quality.

## v41 Ensemble Feedback
- `tools/feedback_loop_v41.py` automates a grid search over `v41_ensemble_feedback` `perf_weighted` variants (now also covers `v42_trend_breakout` combinations and SGD/risk-adjusted metrics).
- Usage: `.venv/bin/python tools/feedback_loop_v41.py --cash 1000 --quick` or `--focused` for a 144-variant sweep.
- Default `v41_ensemble_feedback` hunt config (`perf_lookback=60`, `perf_temperature=0.5`, `perf_forward=3`, `perf_metric=return_per_dd`, `v39b+v39d`): 311.4% return, -13.3% max drawdown, Sharpe 2.72, 139 trades, final $4,114.
- Best `v41` variant found so far (`perf_forward=1`, `perf_metric=raw_return`): 359.2% return, -13.3% max drawdown, Sharpe 2.82, 135 trades, final $4,592.
- `v41` best (359.2% / -13.3% / Sharpe 2.82 / 135 trades, source=yfinance unadjusted) is close to the reconciled `v39d_confluence` (357.5% / -13.4% / Sharpe 2.82 / 135 trades, source=local adjusted); a fair comparison requires re-running `v41` on `source=local`.
- Risk-adjusted `perf_metric` options (`raw_return`, `sharpe`, `sortino`, `calmar`, `return_per_dd`) are available, but `perf_weighted` averaging of two teachers cannot exceed the best teacher unless the weighting is strongly predictive.
- Adding `v42_trend_breakout` to the ensemble (as a third teacher) hurts performance: `v39b+v39d+v42` falls to 183.2% / -16.4% / Sharpe 2.09 with 1,254 trades. Pairwise `v39b+v42` and `v39d+v42` also underperform the `v39b+v39d` baseline.

## v50_high_win_rate (high-win-rate candidate)
- `models/poc_va_macdha/v50_high_win_rate/` is a new wrapper that gates `v45_ultimate_rsi` mean-reversion signals with a `SMA(250)` trend filter (entry-only) and scales target positions to 22.5% of cash (`signal_scale`).
- Verified result at `$1,000` scale on `EQUITY_WINNER_BAG` (2024-08-01 to 2026-07-11, `source=local`, `interval=1H`): **108.7% return**, **-19.5% max drawdown**, **Sharpe 1.87**, **52 trades**, **86.5% win rate**.
- Run: `dmr.run_one(dmr.discover_models(['v50_high_win_rate'])[0], mode='daily', codes=EQUITY_WINNER_BAG, start='2024-08-01', end='2026-07-11', tag='final', cash=1000, source='local', interval='1H')`.
- `v41` was tested as an additional consensus gate but cut trade count to 16 and return to 5.6%; the final model uses `v45` alone.

## v71_live_confidence (live high-WR + confidence sleeve)
- `models/poc_va_macdha/v71_live_confidence/` wraps `v45_ultimate_rsi` with SMA(250) entry-only trend, soft quality floor (`min_score>=1`), and **confidence size-up** (quality + RSI depth → up to 1.55× base scale, cap 40%).
- Frozen variant: `sizeup_q1`. Train/select on 2024-08-01→2025-08-01 only; holdout locked 2025-08-01→2026-07-11 (no retune).
- Verified (`source=local`, `1H`, `$1,000`, `EQUITY_WINNER_BAG`):
  - **Full**: +114.0% ret, −19.5% max DD, Sharpe 1.72, 50 trades, **86.0% WR**, final $2,140
  - **Holdout**: +30.9% ret, −19.6% max DD, Sharpe 1.17, 26 trades, **76.9% WR**
- Live: `SignalEngine.last_confidence[code]` exposes per-trade confidence for desk tickets.
- Vs peers: slightly above `v50` full return (114% vs 109%) with explicit confidence; hard quality=2 (`v70`) hits ~91% WR but **fails** holdout n floor (n=11). **Does not** replace `v39d_confluence` for max return (357%).
- Train/verify: `.venv/bin/python tools/train_v71_live_confidence.py --workers 4 --cash 1000`
- Artifacts: `runs/v71_live_confidence/LEADERBOARD.md`, `models/poc_va_macdha/v71_live_confidence/results.json`.

## v60_microstructure (microstructure / institutional-flow research artifact)
- `models/poc_va_macdha/v60_microstructure/` is a new standalone microstructure model implementing OHLCV-safe OFI, absorption, volume schedule-deviation, VPIN-style toxicity, VPA confirmation, and an XGB meta-classifier with triple-barrier labels.
- Run with `mode="daily"`:
  ```python
  m = dmr.discover_models(["v60_microstructure"])[0]
  dmr.run_one(m, mode="daily", codes=EQUITY_WINNER_BAG, start="2024-08-01", end="2026-07-11", tag="final", cash=1000, source="local", interval="1H")
  ```
- Train: `.venv/bin/python tools/train_v60_microstructure.py --retrain`
- In-sample (full) at `$1,000` on `EQUITY_WINNER_BAG` (2024-08-01 to 2026-07-11, `source=local`, `interval=1H`): **+639.4% return**, **-21.8% max DD**, **Sharpe 2.69**, **105 trades**, **62% win rate**, **final $7,394**.
- Walk-forward OOS (train 2024-08-01 → 2025-08-01, test 2025-08-01 → 2026-07-11, $1,000): **+14.8% return**, **-13.7% max DD**, **Sharpe 0.26**, **13 trades**, **38% win rate**, **final $1,148**.
- Verdict: **research artifact, not promoted.** The OHLCV-only proxies are too noisy to sustain the targeted high precision out-of-sample. The feature module and training pipeline are retained for refinement with tick/Level-2 data.

## Market Runtime (LSE streaming)
- `services/market_runtime/` holds contracts, catalog, ranking, state, persistence, LSE adapter, and supervisor.
- `services/market_runtime/server.py` exports a FastAPI app (`uvicorn services.market_runtime.server:app`)
- Endpoints: `GET /health`, `/coverage`, `/instruments`, `/ticks/{symbol}`, `/bars/{symbol}`, `/opportunities`, and `POST /plan`.
- `POST /plan` runs `tools/live_plan.py` inside the service and returns a full ticket; `apps/trade-desk/src/lib/tradeDesk.ts` calls it when `MARKET_RUNTIME_URL` is set.
- `LSEAdapter` wraps `lse-data` and converts `lse.Tick` into `services.market_runtime.Tick` contracts.
- `StreamSupervisor` streams the catalog (or a symbol list), auto-falls back to `DEGRADED_RANKED` when `max_symbols` is hit, persists ticks to `data/market_runtime.db`, and reports `CoverageHealth`.
- `tools/live_plan.py` now prefers `LSE_API_KEY` candles for live features and falls back to `yfinance` if LSE is unavailable or returns no data.

## Feedback Loop Promotion Gates
- `tools/feedback_loop_arete.py` now applies `PROMOTION_GATES` (min n/trades, return, drawdown, Sharpe, win-rate) and a multi-lock beat of the `v39b` baseline on return, Sharpe, and drawdown before any variant is `promoted`.
- `STATE.json` now includes `promoted`, `promoted_best`, and `promotion_gates`.
- Quick run (2026-07-13) shows `v40_arete_pro` is not promoted because it underperforms `v39b` on return and Sharpe.

## Verification Command
- Re-run the quick loop: `.venv/bin/python tools/feedback_loop_arete.py --quick --cash 1000`
- Re-run the v41 loop: `.venv/bin/python tools/feedback_loop_v41.py --quick --cash 1000`
- Re-run a single model: `dmr.run_one(model, mode="daily", codes=EQUITY_WINNER_BAG, start="2024-08-01", end="2026-07-11", tag="verify", force_1d=False, cash=1000)`
- Run market runtime tests: `python -m unittest discover -s tests -v`

## evolve_direction_v1
- Driver: `runs/evolve_direction_v1/driver.py` with commands `phase0`, `campaign` (2-gen smoke), `campaign-full` (10-gen autonomous).
- Default run: `.venv/bin/python runs/evolve_direction_v1/driver.py --cash 1000000 phase0`.
- `backtest.runner` routes `source="local"` to `CryptoEngine`, which uses `slippage` (not `slippage_us`) and ignores `commission`. `tools/dynamic_model_rank.py` monkey-patches `runner._create_market_engine` so `source="local"` with `us_equity`/`hk_equity` symbols uses `GlobalEquityEngine` for correct `slippage_us` handling while keeping `LocalLoader`/`data_cache`, and patches `backtest.metrics.calc_bars_per_year` so `source="local"` uses the `yfinance` calendar for annualisation (1H = 1764 bars/year).
- Phase 0 baseline at `$1M` (`1H` folds): `v39b_live_adapt` passes 13/13 audit gates (pooled ret ~1.38, max DD ~9.7%, Sharpe ~3.24).
- Smoke campaign: 14 combined variants per generation (7 direction + 7 code mutations); tested 1 generation and best-of-generation `v39b_live_adapt_tight_stop_all` (tight stop 1.0 ATR) passes lockbox/audit (13/13 gates). Code mutation support is in `tools/evolve/mutations.py` (`SignalEngineMutator`, `CODE_MUTATION_MENU`).

## Candidate Event Ledger
- `models/poc_va_macdha/_shared/candidate_ledger.py` is a shared point-in-time ledger used by `v39b_live_adapt` and `v39d_confluence`.
- Each primary `long_entry` candidate is recorded with timestamp, code, entry price, full feature vector (`f_*` columns), meta probability, adjusted probability, meta size, feature multiplier, raw/final size, `passed` flag, and exit outcome.
- `CandidateLedger` flushes to `run_dir/artifacts/candidates.csv` at the end of `SignalEngine.generate()`.
- `tools/dynamic_model_rank.py` copies `candidate_ledger.py` from the model source directory into the run `code/` folder.
- Re-run: `farm.run_one_cached(model, mode="daily", codes=EQUITY_WINNER_BAG, start="2024-08-01", end="2025-08-01", tag="ledger_test", cash=1000, force_1d=True, source="local")`.

## LSE Historical Snapshot/Backfill
- `tools/lse_history.py` fetches `1h`/`1d` candles from LSE (`lse-data`) and writes `data_cache/lse/<interval>/<symbol>.parquet`.
- `tools/lse_history.py snapshot` writes `data_cache/lse/MANIFEST.json` and `data_cache/lse/bridge_config_lse_1h.yaml` / `bridge_config_lse_1d.yaml`.
- `tools/lse_history.py verify` checks manifests and checksums.
- `tools/lse_history.py use-bridge 1h` copies the LSE bridge config to `~/.vibe-trading/data-bridge/config.yaml`.

## Experiment Tracking
- `tools/evolve/experiment_tracking.py` wraps `mlflow` with a file-based tracking URI (`runs/mlruns` by default) and disables via `MLFLOW_DISABLE=1`.
- `farm.run_one_cached()` and `farm.run_batch()` log every run with model id, tag, source, interval, data hash, env versions, and metrics.
- `log_run_from_row()` is used by `farm.py`; metrics include `ret`, `dd`, `sharpe`, `n`, `wr`, `final`, and `reused`.
- View runs: `mlflow ui --backend-store-uri file:///Users/syriljacob/Desktop/TradingAlgoWork/runs/mlruns` (or query `mlflow.search_runs()`).

## Analysis Agent
- `tools/analysis_agent.py` returns a structured **Facts → Decision → Suggestion** report for a single ticker.
- It reuses existing runtime components: `live_plan.plan_symbol` (live features, macro, GEX, risk decision, ticket) and `model_registry.rank_models_for_symbol` (top models).
- It does not modify any model engine or signal file.
- CLI: `.venv/bin/python tools/analysis_agent.py --symbol TSLA --account 1000 --json`
- UI: `apps/trade-desk/src/app/analysis-agent/page.tsx` + `/api/analysis-agent` route.

## Almgren-Chriss Impact Model
- `tools/impact_model.py` provides a simplified Almgren-Chriss temporary + permanent impact calculator (`impact_per_share`) and an optimal-trajectory helper (`optimal_trajectory`).
- `tools/evolve/ac_execution.py` adds `AlmgrenChrissGlobalEquityEngine`, which extends `GlobalEquityEngine` and adds size-dependent impact to the standard fixed slippage.
- `tools/dynamic_model_rank.py` routes US/HK equity runs to this engine when `config["impact_model"] == "almgren_chriss"`.
- Configurable keys: `ac_eta` (temp coeff), `ac_gamma` (perm coeff), `ac_beta` (participation exponent, default 0.5), `ac_adv_days` (default 20), `ac_vol_days` (default 20).
- Example: `dmr.run_one(model, ..., extra_cfg={"impact_model": "almgren_chriss", "ac_eta": 0.1, "ac_gamma": 0.02, "ac_beta": 0.5})`.
- Smoke test (TSLA.US, $100k, 1H, 2024-08-01→2024-09-01): base final $96,492.21 vs AC final $96,487.37 for a 90% target weight, confirming the engine adds impact cost.

## Macro, Cross-Asset, and Long-Memory Feature Module
- New module: `tools/evolve/macro_features.py` with `tools/evolve/macro_features.py` and `MacroCrossAssetEngine`.
- Computes point-in-time: macro surprise/event proximity, rolling beta/correlation to SPY/TLT, VIX/rate/equity regime features, fractional-differencing long-memory features, and interaction terms (high-beta × macro surprise × low VIX, etc.).
- Causal contracts: all returns are lagged before rolling windows; macro surprises are joined via backward `merge_asof`; fractional `d` is fit on a training window only (default `hurst`; `adf` method requires `statsmodels`).
- Tests: `tests/test_macro_features.py` (9 tests pass).
- Integration path: use `MacroCrossAssetEngine.fit(train)` then `transform(target, spy, tlt, vix, events)` in a purged walk-forward loop; wire into `feature_validation.py` by aligning cross-asset parquet bars and adding `macro_features` to `FEATURE_FAMILIES` when ready.
- Focused test plan: (1) add a v61 research script that loads `EQUITY_WINNER_BAG` + `SPY/TLT/VIX` + macro CSV and runs `macro_feature_matrix` per fold; (2) baseline: v39d_confluence on same fold; (3) candidate: v39d features + macro features with a small meta-logistic; (4) gates: beat baseline on event-period Sharpe/return and pass subperiod analysis (event vs non-event).

## `tools/institutional_flow` (reusable OHLCV-safe microstructure feature module)
- Module: `tools/institutional_flow/features.py` with `compute_features(df, params)` returning point-in-time VPIN, OFI, absorption, VPA confirmation, schedule deviation, regime, and fractional-diff columns.
- Module: `tools/institutional_flow/impact.py` wrapping `tools/impact_model.py` (`impact_per_share`, `cost_for_trade`, `optimal_trajectory`, `estimate_adv`, `estimate_volatility`).
- Tests: `tests/test_institutional_flow.py` (12 tests pass, including causality and timezone checks).
- Pilot model: `models/poc_va_macdha/v61_institutional_flow/` uses `tools/institutional_flow.compute_features` with a heuristic classifier.
- Pilot run: `.venv/bin/python tools/institutional_flow/run_pilot.py`.
- Pilot result (2025-08-01 → 2026-07-11, `source=local`, `1H`, TSLA/SPY/QQQ, $1,000):
  - `v60_microstructure`: +19.7% ret, -9.0% max DD, Sharpe 1.95, 74% WR, 19 trades
  - `v39d_confluence`: -1.6% ret, -7.8% max DD, Sharpe -0.27, 39% WR, 28 trades
  - `v61_institutional_flow` (standard): +4.0% ret, -14.1% max DD, Sharpe 0.35, 40% WR, 162 trades
  - `v61_institutional_flow` + Almgren-Chriss impact: +4.0% ret, -14.1% max DD, Sharpe 0.35, final $1,040 (impact cost $0.04 at $1k scale)
- Verdict: `v61` is a working refactor/proof-of-concept, but the heuristic is not yet competitive with `v60` or `v39d`. The AC impact overlay is correctly active but negligible at $1k scale.
