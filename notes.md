# Notes: High-Win-Rate Model Search

## Current Champions (from AGENTS.md)
- `v39d_confluence` — best single model: 357.5% return, -13.4% max DD, Sharpe 2.82, 135 trades, **67% win rate**.
- `v41_ensemble_feedback` best `perf_weighted` (`v39b+v39d`, `perf_forward=1`, `perf_metric=raw_return`): 359.2% / -13.3% / Sharpe 2.82 / 135 trades / 67% win rate.
- `v39b_live_adapt`: 309.7% / -13.1% / Sharpe 2.70 / 67% win rate.
- `v44_absorption` (OHLCV order-flow overlay): 262.7% / -17.8% / Sharpe 2.24 / 158 trades — not promoted.
- `v42_trend_breakout`: standalone 7.4% / -37.8% / Sharpe 0.28 / 161 trades; ensemble with `v39b`/`v39d` underperforms.
- `v40_arete_pro` underperforms `v39b`.

## Repo Has Evolved Beyond AGENTS.md
Discovered additional models in `models/poc_va_macdha/`:
- `v39d_causal`, `v39b_live_adapt_tight_stop_all`, `v39d_confluence_tight_stop_all`
- `v43_order_blocks`, `v44_absorption`, `v44_true_levels`
- `v45_ultimate_rsi`, `v45b_ultimate_rsi_stops`
- `v46_lux_pivot_ghosts`
- `v47_causal`, `v47_high_freq_edge`
- `v48_regime_barbell`
- `v49_precision_trend`
- `tools/feedback_loop_v48.py`, `tools/feedback_loop_v49_precision.py`, `tools/evolve/v48_execution.py` exist.

## Existing Feedback Loop / Search Tools
- `tools/feedback_loop_v41.py` — grid search over `v41_ensemble_feedback` variants, risk-adjusted metrics.
- `tools/feedback_loop_arete.py` — `v39b` baseline vs `v40_arete_pro` variants, with `PROMOTION_GATES`.
- `tools/feedback_loop_v48.py` — `v48_regime_barbell` research with `CausalGlobalEquityEngine`.
- `tools/feedback_loop_v49_precision.py` — pre-registered high-precision v49 causal evaluation.
- `tools/evolve/farm.py` and `runs/evolve_direction_v1/driver.py` — multi-generation model ranking and mutation.
- `tools/dynamic_model_rank.py` (`dmr`) — `run_one(model, mode, codes, start, end, tag, cash, force_1d)`.
- `models/poc_va_macdha/_shared/candidate_ledger.py` — point-in-time ledger with `meta_prob`, `adjusted_prob`, `f_*`, `passed`, exit outcomes.

## Win-Rate Levers to Investigate
- **Confidence threshold** on `meta_prob` / `adjusted_prob` to drop low-probability entries.
- **Consensus filter** (e.g., `v39b` and `v39d` both agree with high probability).
- **Post-hoc trade outcome classifier** trained on `candidate_ledger` `f_*` features.
- **Tighter take-profit / looser stop-loss** adjustments to skew win rate (but may reduce expectancy).
- **Ensemble of high-win-rate sub-variants** found by `feedback_loop_v41` or `evolve_direction_v1`.
- **Only long entries** in strongest-trend regimes; avoid choppy / counter-trend signals.

## v39d Confluence Mechanics (confirmed live run)
- Confirmed `v39d_confluence` on `source=local` 1H $1,000: 357.5% ret, -13.4% DD, Sharpe 2.82, 135 trades, 67% WR.
- `meta_config.json` threshold = 0.50; `_prob_to_size` uses `skip = min(thr, _GENOME["meta_p_skip"])` where `meta_p_skip = 0.50` and `meta_p_full = 0.68`.
- Raising `threshold` in `meta_config.json` alone does **not** raise the gate because `skip` is capped at 0.50; a hard `adj_proba` gate or `_GENOME` change is needed.
- `v41_ensemble_feedback` has `sgd_binary` / `sgd_proba` modes with a `proba_threshold` parameter; `perf_weighted` blends teachers.

## Environment
- M1 Pro, 8 cores, 16 GB RAM, 3.17 GB available, disk 99.3% full (3.02 GB free).
- `.venv` (Python 3.13) has `backtest` installed; `v39d` runs correctly with `source=local` / `interval=1H`.
- Git branch `prod-ready-v1`.

## v50_high_win_rate (final candidate)
- **Result**: `v50_high_win_rate` on `EQUITY_WINNER_BAG`, `source=local`, `interval=1H`, `$1,000` (2024-08-01 -> 2026-07-11): **108.7% return**, **-19.5% max drawdown**, **86.5% win rate**, **52 trades**, Sharpe 1.87, Calmar 2.40.
- **Engine**: `models/poc_va_macdha/v50_high_win_rate/signal_engine.py` loads `v45_ultimate_rsi` as the primary signal, gates new entries by `close > SMA(250)` (trend filter at entry only), and outputs a target position of 22.5% of cash per trade (`signal_scale` 0.225).
- **Tuning notes**: The raw `v45_ultimate_rsi` had 76.7% WR / 157.4% ret / -44.9% DD / 103 trades. Adding a `SMA(250)` entry filter raised WR to 86.5% but cut trade count to 52; scaling position size to 22.5% of cash brought drawdown from ~-48% to -19.5% while keeping return positive.
- **v41 gate**: Adding `v41_ensemble_feedback` as a consensus gate with `threshold=0.0` reduced trades to 16 and return to 5.6%, so `v41` was not used in the final configuration.
- **Trade-off**: The final model has a higher win rate than the best existing equity model but lower return and fewer trades than `v39d_confluence` / `v41`. It satisfies the stated target constraints (>80% WR, ≥30 trades, positive return, <20% DD).

## Risks
- Overfitting to a 2-year equity bag.
- Disk exhaustion if many runs are generated.
- High win rate often comes at the cost of fewer trades and lower expectancy; must verify economic significance.
- `v50` is a `v45` wrapper; out-of-sample performance depends on `v45` and the `SMA(250)` trend filter continuing to behave.
