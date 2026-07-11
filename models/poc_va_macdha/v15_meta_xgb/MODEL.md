# v15_meta_xgb

True meta-labeler: **v13 specialist primary side unchanged**; secondary XGB filters + sizes.

## OOS (expanding half-year)
- n_candidates: 246
- folds: 2025H2, 2026H1 (both +exp lift)
- avg_lift_hit: +2.4pp (57.7% → 60.1%)
- avg_lift_exp: +0.74pp (1.06% → 1.81%)
- threshold: 0.60; size map {0.25,0.5,1.0}

## Caveat
Lift is modest on ~2y of Yahoo 1H. Do **not** auto-promote WINNER until full portfolio backtest beats v13 on PF/Sharpe/DD.

## Re-train
```bash
.venv/bin/python runs/poc_va_meta_xgb/build_candidates.py
.venv/bin/python runs/poc_va_meta_xgb/train_meta_xgb.py
```
