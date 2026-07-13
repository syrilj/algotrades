# Agent Notes for TradingAlgoWork

## Backtest Entry Points
- `backtest.runner.py` is the main runner. It reads `config.json` and loads `signal_engine.py`.
- `tools/dynamic_model_rank.py` (`dmr`) provides `run_one(model, mode, codes, start, end, tag, cash, force_1d)`.
- `tools/evolve/pipeline.py` / `tools/evolve/farm.py` manage multi-generation model ranking and evolution.

## Current Champion Equity Model
- `models/poc_va_macdha/v41_ensemble_feedback/` is the current winner.
- Reported result at `$1,000` scale on `EQUITY_WINNER_BAG`: 367.3% return, -13.3% max drawdown, Sharpe 2.80, 135 trades, 67% win rate.
- `EQUITY_WINNER_BAG` in `tools/evolve/farm.py` is `["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "XLP.US", "QQQ.US"]`."}  I need to fix the JSON? The tool expects string. Let's continue. Wait, the `edit` tool new string has unmatched quote at the end? Let's use `write` instead? The `edit` tool `new_string` ends with `

## Arete Feedback Loop
- `tools/feedback_loop_arete.py` runs `v39b` baseline against `v40_arete_pro` variants.
- Usage: `.venv/bin/python tools/feedback_loop_arete.py --cash 1000` (use `--quick` for baseline + full v40 only).
- Outputs `runs/feedback_loop_arete/LEADERBOARD.md` and `STATE.json`.

## Key Findings (2026-07-12 run)
- `v40_arete_pro` (Arete overlay on `v39b`) underperforms the baseline on return.
- Best `v40` variant was `v40_ma_only` (216% vs `v39b` 310%), but with higher drawdown and lower Sharpe.
- The Arete MA/Fib/SOX gates are too restrictive for the `v39b` signal set; they reduce trade count and final return.
- No current model approaches the "$1000 to $1M" target. The best equity backtest turns $1000 into ~$4,673 in two years (v41_ensemble_feedback).

## v42 Trend Breakout
- `models/poc_va_macdha/v42_trend_breakout/` is a new teacher model built to break the correlation plateau between `v39b` and `v39d`.
- Standalone backtest on `EQUITY_WINNER_BAG`: 7.4% return, -37.8% max drawdown, Sharpe 0.28, 161 trades — not a useful standalone teacher.
- `v42` was integrated into the `v41_ensemble_feedback` sweep; every tested combination with `v42` underperforms the `v39b+v39d` baseline.
- Conclusion: `v42_trend_breakout` is not selected for the current ensemble; keep it as a research artifact for future signal decomposition.

## v41 Ensemble Feedback
- `tools/feedback_loop_v41.py` automates a grid search over `v41_ensemble_feedback` `perf_weighted` variants (now also covers `v42_trend_breakout` combinations and SGD/risk-adjusted metrics).
- Usage: `.venv/bin/python tools/feedback_loop_v41.py --cash 1000 --quick` or `--focused` for a 144-variant sweep.
- Best `v41_ensemble_feedback` config on `EQUITY_WINNER_BAG` ($1000, 2024-08-01 to 2026-07-11): 367.3% return, -13.3% max drawdown, Sharpe 2.80, 135 trades, final $4,673.
- The `perf_weighted` ensemble of `v39b_live_adapt` + `v39d_confluence` now beats the best single teacher (`v39d_confluence`: 357.5% / -13.4% / Sharpe 2.82) when `perf_metric` is set to `return_per_dd`.
- Risk-adjusted `perf_metric` options (`raw_return`, `sharpe`, `sortino`, `calmar`, `return_per_dd`) were added; the `return_per_dd` lookback with `perf_lookback=60`, `perf_temperature=0.5`, `perf_forward=3` produces the highest score on the current bag.
- Adding `v42_trend_breakout` to the ensemble (as a third teacher) hurts performance: `v39b+v39d+v42` falls to 183.2% / -16.4% / Sharpe 2.09 with 1,254 trades. Pairwise `v39b+v42` and `v39d+v42` also underperform the `v39b+v39d` baseline.
- Current champion: `v41_ensemble_feedback` with `base_models=["v39b_live_adapt", "v39d_confluence"]` in `perf_weighted` mode (hunt_config: `perf_lookback=60`, `perf_temperature=0.5`, `perf_forward=3`, `perf_metric=return_per_dd`).

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
