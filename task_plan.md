# Task Plan: High-Win-Rate Model via Multi-Model Feedback Loop

## Goal
Build a `v45_high_win_rate` model/variant (or a tuned feedback-loop variant) that synthesises all existing models (`v39b`, `v39d`, `v42`, `v44`, `v41` ensemble) and iterates toward a **really high win rate** on the `EQUITY_WINNER_BAG` backtest (`source=local`, `interval=1H`, `$1,000` scale) while keeping enough return and manageable drawdown.

## Phases
- [x] Phase 1: Plan and resource-aware setup
- [x] Phase 2: Research existing models, feedback loops, and win-rate levers
- [x] Phase 3: Design candidate strategies (filters, thresholds, ensembles, meta-learners)
- [x] Phase 4: Implement `v50_high_win_rate` wrapper around `v45_ultimate_rsi`
- [x] Phase 5: Run targeted search / evaluation in parallel
- [x] Phase 6: Report and iterate

## Key Questions
1. What is the win-rate target and what are acceptable trade-offs (return, trade count, drawdown)?
2. Which existing models have the highest per-trade win-rate, and where do they lose?
3. Can a confidence / consensus / post-hoc filter raise win rate above the best teacher?

## Decisions Made
- Default success target: **>80% win rate** on `EQUITY_WINNER_BAG` with at least 30 trades, positive return, and drawdown <20%.
- Resource constraints: only 3.02 GB disk free and 3.17 GB RAM available, so runs must be lightweight, tagged, and old run artifacts pruned as needed.
- Search strategy: use existing `dmr`/`farm` runners and `feedback_loop` infrastructure; do not rewrite a full backtest engine.
- Phase 2 findings: the repo has advanced beyond AGENTS.md (v45-v49 exist). `v39d_confluence` is confirmed at 67% WR / 357.5% ret on `source=local` 1H $1k. `v41` is a meta-ensemble with `proba_threshold` for SGD modes. `v39d` sizing uses `adj_proba` and `_prob_to_size`; the true gate is `_GENOME["meta_p_skip"]` (0.50), so a hard confidence gate must be added or `_GENOME` changed.
- Phase 3 design: (1) screen all equity-runnable models v39-v49 on `EQUITY_WINNER_BAG` to find the highest-WR baseline; (2) if baseline < target, add a point-in-time confidence gate or build a `v50` wrapper that only takes entries in a strong trend regime.
- Phase 4 implementation: `models/poc_va_macdha/v50_high_win_rate/` created with `signal_engine.py` and `hunt_config.json`. It loads `v45_ultimate_rsi` as the primary signal, applies a `close > SMA(250)` trend filter at entry (so a dip must still occur within an uptrend), and scales the resulting position to 22.5% of cash per trade (`signal_scale`).
- Phase 5 results (source=local, interval=1H, $1,000, 2024-08-01 -> 2026-07-11):
  - `v50_high_win_rate` final: **108.7% return**, **-19.5% max drawdown**, **86.5% win rate**, **52 trades**, Sharpe 1.87, Calmar 2.40.
  - This beats the target constraints (>80% WR, >=30 trades, positive return, <20% DD).

## Errors Encountered
- None yet.

## Status
**Complete.** A `v50_high_win_rate` model has been implemented, tuned, and verified on `EQUITY_WINNER_BAG` with 86.5% WR, 108.7% return, -19.5% DD, and 52 trades.
