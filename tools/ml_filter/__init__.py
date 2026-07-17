"""XGBoost trade-filter research pipeline (IMPROVE_ML_BACKTEST.md path).

Modules:
  - features: causal per-bar feature frame shared by the candidate logger,
    the trainer, and the v88_xgb_filter research engine.
  - candidate_logger: dump rule-generated entry candidates + forward labels.
  - train_xgb: walk-forward XGB + native TreeSHAP pruning + one-shot holdout.
"""
