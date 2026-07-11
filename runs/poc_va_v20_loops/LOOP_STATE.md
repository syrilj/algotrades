# LSE improvement loops — session state (2026-07-11)

## User ask
Find current best model → research londonstrategicedge.com/machine-learning techniques → run multiple
feedback loops trying approaches → deliver model with best win rate + Sharpe for live trading.
Use prior failure notes (findings.jsonl, FAILURE_PROTOCOL, RESEARCH_NEXT).

## Status
- [x] Task 1: infra mapped. WINNER = v15_meta_xgb (Sharpe 2.128, WR 62.3%, PF 2.68, DD -13.2%, n=130,
      window 2024-08..2026-07 1H; long 1D 2020-2026: Sharpe 0.75, PF 1.70, DD -22%). Backtest reproduces exactly.
- [x] Task 2: 28 LSE ML pages fetched to scratchpad `/private/tmp/claude-501/-Users-syriljacob-Desktop-TradingAlgoWork/1a0a1b1f-9300-44a5-8293-4ec179a4da7e/scratchpad/lse/`
      (browse skill; gstack browse binary `$HOME/.claude/skills/gstack/browse/dist/browse`).
- [~] Research-digest Workflow run wf_a8f50ee9-e3e: 6 digest agents done, synthesis agent pending.
      Journal: `~/.claude/projects/-Users-syriljacob-Desktop-TradingAlgoWork/1a0a1b1f-9300-44a5-8293-4ec179a4da7e/subagents/workflows/wf_a8f50ee9-e3e/journal.jsonl`
      (synthesis = 7th result; returns ranked `experiments` list with id/hypothesis/layer/implementation_sketch/pass_criteria).
- [x] Task 3: experiment design saved to runs/poc_va_v20_loops/EXPERIMENTS.json (12 ranked, 15 discarded).
- [~] Task 4: experiment Workflow wf_8fefb0e2-b25 RUNNING: 8 parallel agents (v20_soft_nodemand,
      v21_calibrated_size, v22_volz_size, v23_corr_throttle, v24_inverse_vol_budgets, v25_vol_target,
      v27_htf_climax_exit, wf_purged_stitch_baseline) then v29_combo combiner. Engines in
      runs/poc_va_v20_loops/engines/<id>/; per-run results in runs/<id>__<window>/loop_summary.json.
      Journal: ~/.claude/projects/-Users-syriljacob-Desktop-TradingAlgoWork/1a0a1b1f-9300-44a5-8293-4ec179a4da7e/subagents/workflows/wf_8fefb0e2-b25/journal.jsonl
- [ ] Task 5: validate: PASS_BAR + long1d + split-half stability + anti-overfit holdout.
- [ ] Task 6: record findings via tools/findings.py, update WINNER.json/MODEL.md, final report.

## Key infra facts
- Backtest: `.venv/bin/python -c "from pathlib import Path; from backtest.runner import main; main(Path('runs/<dir>').resolve())"`.
  Run dir needs config.json + code/signal_engine.py (+ meta_config.json + meta_xgb_final.json copied beside it).
- Data: yfinance, refetch OK; enable parquet cache via env `VIBE_TRADING_DATA_CACHE=1`.
- Harness (validated): `.venv/bin/python runs/poc_va_v20_loops/harness.py --name vXX --code-from <codedir> --window std|long1d|firsthalf|secondhalf --config-extra '{...}'`
  → prints/writes loop_summary.json with metrics, PASS_BAR check, vs_v15 deltas.
- Engine mechanics: signal Series = target weight in [0,1] per symbol, shifted 1 bar; weights normalized only when sum>1.
  Portfolio optimizers exist (`optimizer` key in config): equal_volatility, risk_parity, mean_variance, max_diversification,
  turnover_aware (params via optimizer_params). NEVER used in repo before = untried lake.
- Preflight done: v15 + risk_parity → return 276% (vs 130%), WR 62.6%, but Sharpe 1.79, DD -26% (DD gate fail).
  Optimizer re-normalizes to fully-invested → more return/DD. Need hybrid (e.g. cap gross, blend with meta size).
- v15 engine levers: `_prob_to_size` step map (thr 0.6, breaks 0.55/0.65), meta_config.json feat_cols (18),
  per-symbol _ROUTING dict, exits (htf red, vwap break, HA red+htf, red_flag).
- Sharpe = mean/std * sqrt(bars_per_year) on portfolio bar returns (metrics.py).

## Constraints (from findings.jsonl — do not violate)
- Architecture locked: rules primary (side) → meta XGB (whether/size) → risk. No price-predicting ML primary.
- PASS_BAR (all, OOS): PF>1.2, |DD|<0.25, Sharpe>0.5, n>=40, expectancy>0. WR alone = vanity.
- FAILED before: naive XGB price prediction; hard vol/EMA200 gates on v15; full Coulling stack on 1H;
  WR>=90 forcing (n<40 noise); v19 node-cloud reactive primary; random k-fold; threshold tuned on test.
- WORKING: specialist routing; meta-XGB on engine-exit labels; half-Kelly/ATR overlay (DD↓ Sharpe↓ slightly);
  light Coulling no-demand (PF↑ capacity↓); vol_z>=1 meta; v18 sniper satellite (83% WR n=12).
- Promotion: beat v15 Sharpe 2.128 on std window AND pass long1d stress AND split-half stability AND PASS_BAR everywhere.
- After 3 fails on same hypothesis class → stop, re-research (FAILURE_PROTOCOL.md).

## Planned experiment families (pre-synthesis; merge with synthesis output)
1. Portfolio layer: optimizer variants + optimizer_params sweeps; hybrid = optimizer output rescaled to respect meta size
   (cap gross exposure ~<=1.0, or lookback tweaks). Target: keep return lift, cut DD below 0.25 → Sharpe > 2.13.
2. Meta sizing: continuous/Kelly-like p→size mapping; probability calibration; threshold/size_breaks sweep
   (train-only tuning, validate OOS).
3. Soft overlays (lake A): size ×0.5 on no_demand instead of hard block; vol_z sizing.
4. Risk: ATR trail softened; portfolio vol targeting.
5. Validation upgrades: WF-stitched portfolio; purged/embargo CV when retraining boosters.

## Deliverable
New model dir models/poc_va_macdha/v2X_*/ + updated WINNER.json only if all gates clear; final report with honest
caveats (backtest ≠ live; not financial advice). Record every experiment via tools/findings.py (status auto).
