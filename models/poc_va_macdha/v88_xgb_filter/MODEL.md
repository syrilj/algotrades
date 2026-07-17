# v88_xgb_filter

**Status: RESEARCH ONLY — NOT PROMOTED.** Do not route live capital, do not
add to DEPLOYMENT_MANIFEST.json, WINNER.json, or DESK_ROUTING.json without a
full promotion review.

v72_dual_sleeve weights re-ranked by a frozen XGBoost entry filter — the
`IMPROVE_ML_BACKTEST.md` path ("XGB as trade filter/ranker, not a strategy"),
plan item P2-9.

## Pipeline

1. `tools/ml_filter/candidate_logger.py` — one row per v72 flat→long entry on
   the locked contract (local 1H, 2024-08-01 → 2026-07-11). Features are
   causal (bar *t* only; fills at *t+1* open); label = rule-exit round trip
   beats a 15 bps cost buffer. 175 candidates: 92 train / 83 holdout,
   base rate 0.72.
2. `tools/ml_filter/train_xgb.py` — expanding-window walk-forward CV on
   **train-window rows only** (4 folds), shallow regularized trees
   (eta 0.05, depth 3, L1/L2 on), feature pruning by mean |SHAP| (xgboost
   native TreeSHAP, `pred_contribs=True`), acceptance threshold picked on
   pooled validation predictions only. Artifacts: `xgb_filter.json` +
   `filter_meta.json` (features, threshold, params).
3. This engine — loads the frozen booster; entries scoring `< threshold` are
   sized at `low_scale` (0.5) of the v72 weight for the whole segment
   (**ranker, not gate**; no v72 entry is ever added or fully removed).
   Fail-soft: missing booster ⇒ raw v72 weights, `filter_active = False`.

## One-shot holdout evaluation (frozen model + threshold; reported verbatim)

Source: `runs/v88_xgb_filter/TRAIN_REPORT.json` (2026-07-16). Threshold 0.70.

| Cell | n | WR | mean R | sum R |
|------|---|----|--------|-------|
| All holdout candidates (baseline) | 83 | 71.1% | +2.98% | +2.474 |
| Filter-accepted (p ≥ 0.70) | 47 | **78.7%** | **+4.50%** | +2.115 |

Honest read:

- Per-trade quality improves (WR +7.6 pp, mean R +1.5 pp) — the filter ranks.
- Total candidate-pool return is **lower** (accepted sum R 2.115 vs 2.474):
  the filter trades less. At 0.5x sizing (this engine) the give-up is half
  that, but a full portfolio backtest has **not** been run yet.
- Walk-forward AUC was ~0.5 on the two earliest (tiny) folds, ~0.65–0.67 on
  the later folds — 92 training rows is thin; treat this as a promising
  direction, not proof. Top SHAP features: `dist_vwap_atr`, `dist_ema22_atr`,
  `dist_hh20_atr`, `macd_hist_atr`, `engine_conf`.

## Next steps before any promotion talk

1. Portfolio-level backtest of this engine on the locked contract
   (`dynamic_model_rank.run_one` with `v88_xgb_filter`) — compare OOS
   PF / DD / Sharpe vs v72, not just per-candidate stats.
2. Regrow the candidate pool (shadow-ledger rows, P1-7) to > 400 before
   trusting the probabilities; this also feeds the real calibrator.
3. Findings record via `tools/findings.py` after the portfolio run.

## Run

```bash
.venv/bin/python tools/ml_filter/candidate_logger.py
.venv/bin/python tools/ml_filter/train_xgb.py
```
