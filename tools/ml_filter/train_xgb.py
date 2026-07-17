#!/usr/bin/env python3
"""Walk-forward XGBoost trade filter with native-TreeSHAP pruning (research only).

Discipline (IMPROVE_ML_BACKTEST.md + docs/ML_PROD_READINESS_PLAN.md P2-9):
  - Fit and tune on **train-window candidates only** (entry_ts inside the
    locked train window). Holdout rows are touched exactly once, at the end,
    with the fully frozen model + threshold — a one-shot evaluation whose
    result is reported as-is, pass or fail.
  - Time-ordered walk-forward CV (expanding train, next-block validation);
    never random k-fold.
  - Shallow, regularized trees; low learning rate.
  - Feature pruning by mean |SHAP| using xgboost's exact TreeSHAP
    (``pred_contribs=True``) — no external shap dependency.
  - Acceptance threshold chosen on pooled validation predictions only.

This tool never touches DEPLOYMENT_MANIFEST.json, WINNER.json, or any locked
run artifact, and performs no promotion. Output is a research bundle under
models/poc_va_macdha/v88_xgb_filter/ plus a report under runs/v88_xgb_filter/.

Usage:
  .venv/bin/python tools/ml_filter/train_xgb.py
  .venv/bin/python tools/ml_filter/train_xgb.py --candidates runs/v88_xgb_filter/candidates.csv
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from ml_filter.features import FEATURE_COLUMNS  # noqa: E402

CANDIDATES_PATH = ROOT / "runs" / "v88_xgb_filter" / "candidates.csv"
BUNDLE_DIR = ROOT / "models" / "poc_va_macdha" / "v88_xgb_filter"
REPORT_PATH = ROOT / "runs" / "v88_xgb_filter" / "TRAIN_REPORT.json"

XGB_PARAMS = {
    "objective": "binary:logistic",
    "eval_metric": "logloss",
    "eta": 0.01,       # Slower learning rate for longer, more robust training
    "max_depth": 3,
    "min_child_weight": 5,
    "subsample": 0.9,
    "colsample_bytree": 0.9,
    "lambda": 2.0,
    "alpha": 1.0,
    "seed": 7,
}
MAX_ROUNDS = 1500     # 5x more max rounds
EARLY_STOP = 100      # Larger patience to prevent premature stopping
N_FOLDS = 4
MIN_TRAIN_ROWS = 60
MIN_ACCEPTED_FOR_THRESHOLD = 20
THRESHOLD_GRID = [round(x, 2) for x in np.arange(0.40, 0.76, 0.05)]


def walk_forward_folds(n: int, n_folds: int = N_FOLDS) -> list[tuple[np.ndarray, np.ndarray]]:
    """Expanding-window folds over time-sorted rows: train [0:cut), val [cut:next)."""
    if n < (n_folds + 1) * 10:
        n_folds = max(2, n // 20)
    edges = np.linspace(0, n, n_folds + 2, dtype=int)  # first block is seed train
    folds: list[tuple[np.ndarray, np.ndarray]] = []
    for k in range(1, n_folds + 1):
        train_idx = np.arange(0, edges[k])
        val_idx = np.arange(edges[k], edges[k + 1])
        if len(train_idx) >= 10 and len(val_idx) >= 5:
            folds.append((train_idx, val_idx))
    return folds


def _train_booster(X_train, y_train, X_val, y_val, features: list[str]):
    import xgboost as xgb

    dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=features)
    dval = xgb.DMatrix(X_val, label=y_val, feature_names=features)
    booster = xgb.train(
        XGB_PARAMS,
        dtrain,
        num_boost_round=MAX_ROUNDS,
        evals=[(dval, "val")],
        early_stopping_rounds=EARLY_STOP,
        verbose_eval=False,
    )
    return booster


def mean_abs_shap(booster, X, features: list[str]) -> dict[str, float]:
    """Exact TreeSHAP via xgboost (last column is the bias term — dropped)."""
    import xgboost as xgb

    contribs = booster.predict(xgb.DMatrix(X, feature_names=features), pred_contribs=True)
    magnitudes = np.abs(contribs[:, :-1]).mean(axis=0)
    return {name: float(value) for name, value in zip(features, magnitudes)}


def run_walk_forward(
    table: pd.DataFrame, features: list[str]
) -> tuple[list[dict[str, Any]], pd.DataFrame, dict[str, float]]:
    """Walk-forward CV on time-sorted train rows.

    Returns per-fold stats, the pooled out-of-fold validation predictions,
    and mean |SHAP| per feature (averaged over folds).
    """
    X = table[features].to_numpy(dtype=float)
    y = table["label"].to_numpy(dtype=int)
    folds = walk_forward_folds(len(table))
    fold_stats: list[dict[str, Any]] = []
    pooled: list[pd.DataFrame] = []
    shap_totals: dict[str, float] = {name: 0.0 for name in features}

    import xgboost as xgb

    for i, (train_idx, val_idx) in enumerate(folds):
        booster = _train_booster(X[train_idx], y[train_idx], X[val_idx], y[val_idx], features)
        preds = booster.predict(
            xgb.DMatrix(X[val_idx], feature_names=features),
            iteration_range=(0, booster.best_iteration + 1),
        )
        val_frame = table.iloc[val_idx][["entry_ts", "realized_return", "label"]].copy()
        val_frame["p_win"] = preds
        pooled.append(val_frame)
        for name, value in mean_abs_shap(booster, X[train_idx], features).items():
            shap_totals[name] += value
        base = float(y[val_idx].mean())
        try:
            from sklearn.metrics import roc_auc_score

            auc = float(roc_auc_score(y[val_idx], preds)) if len(set(y[val_idx])) > 1 else None
        except Exception:  # noqa: BLE001
            auc = None
        fold_stats.append(
            {
                "fold": i,
                "train_n": int(len(train_idx)),
                "val_n": int(len(val_idx)),
                "val_base_rate": base,
                "val_auc": auc,
                "best_iteration": int(booster.best_iteration),
            }
        )
    shap_mean = {k: v / max(len(folds), 1) for k, v in shap_totals.items()}
    pooled_frame = pd.concat(pooled, ignore_index=True) if pooled else pd.DataFrame()
    return fold_stats, pooled_frame, shap_mean


def prune_features(shap_mean: dict[str, float], keep_top: int = 10) -> list[str]:
    """Keep the top-``keep_top`` features by mean |SHAP| (non-zero only)."""
    ranked = sorted(shap_mean.items(), key=lambda kv: kv[1], reverse=True)
    kept = [name for name, value in ranked[:keep_top] if value > 0.0]
    return kept if len(kept) >= 3 else [name for name, _ in ranked[:3]]


def select_threshold(pooled: pd.DataFrame) -> dict[str, Any]:
    """Pick the acceptance threshold on pooled validation predictions only.

    Maximizes mean realized return of accepted candidates subject to a
    minimum accepted count; falls back to 0.5 when no threshold qualifies.
    """
    best: dict[str, Any] | None = None
    for threshold in THRESHOLD_GRID:
        accepted = pooled[pooled["p_win"] >= threshold]
        if len(accepted) < MIN_ACCEPTED_FOR_THRESHOLD:
            continue
        mean_r = float(accepted["realized_return"].mean())
        row = {
            "threshold": threshold,
            "accepted_n": int(len(accepted)),
            "accepted_mean_r": mean_r,
            "accepted_wr": float(accepted["label"].mean()),
        }
        if best is None or mean_r > best["accepted_mean_r"]:
            best = row
    if best is None:
        best = {"threshold": 0.5, "accepted_n": 0, "accepted_mean_r": None, "accepted_wr": None,
                "note": "no threshold met the minimum accepted count; defaulted to 0.5"}
    return best


def one_shot_holdout_eval(
    booster, holdout: pd.DataFrame, features: list[str], threshold: float
) -> dict[str, Any]:
    """The single permitted holdout touch. Reported verbatim — no retuning after."""
    import xgboost as xgb

    if holdout.empty:
        return {"error": "no_holdout_candidates"}
    X = holdout[features].to_numpy(dtype=float)
    preds = booster.predict(xgb.DMatrix(X, feature_names=features))
    accepted_mask = preds >= threshold
    baseline = {
        "n": int(len(holdout)),
        "wr": float(holdout["label"].mean()),
        "mean_r": float(holdout["realized_return"].mean()),
        "sum_r": float(holdout["realized_return"].sum()),
    }
    accepted = holdout[accepted_mask]
    filtered = {
        "n": int(len(accepted)),
        "wr": float(accepted["label"].mean()) if len(accepted) else None,
        "mean_r": float(accepted["realized_return"].mean()) if len(accepted) else None,
        "sum_r": float(accepted["realized_return"].sum()) if len(accepted) else None,
    }
    improves = (
        filtered["mean_r"] is not None
        and filtered["n"] >= 20
        and filtered["mean_r"] > baseline["mean_r"]
        and filtered["wr"] > baseline["wr"]
    )
    return {
        "note": "one-shot evaluation; model and threshold were frozen before this cell ran",
        "threshold": threshold,
        "baseline_all_candidates": baseline,
        "filter_accepted": filtered,
        "improves_over_baseline": bool(improves),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Walk-forward XGB trade filter (research)")
    parser.add_argument("--candidates", default=str(CANDIDATES_PATH))
    parser.add_argument("--bundle-dir", default=str(BUNDLE_DIR))
    parser.add_argument("--report", default=str(REPORT_PATH))
    parser.add_argument("--keep-top", type=int, default=10)
    args = parser.parse_args(argv)

    table = pd.read_csv(args.candidates)
    table = table.sort_values("entry_ts").reset_index(drop=True)
    train = table[table["window"] == "train"].reset_index(drop=True)
    holdout = table[table["window"] == "holdout"].reset_index(drop=True)

    report: dict[str, Any] = {
        "schema_version": "xgb-filter-train-v1",
        "asof_utc": datetime.now(timezone.utc).isoformat(),
        "candidates": str(args.candidates),
        "rows": {"train": int(len(train)), "holdout": int(len(holdout))},
        "params": XGB_PARAMS,
        "status": "research_only_not_promoted",
    }

    if len(train) < MIN_TRAIN_ROWS:
        report["error"] = f"insufficient_train_candidates: {len(train)} < {MIN_TRAIN_ROWS}"
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 1

    # Pass 1: walk-forward on all features → SHAP ranking.
    fold_stats, pooled, shap_mean = run_walk_forward(train, FEATURE_COLUMNS)
    report["walk_forward_all_features"] = fold_stats
    report["shap_mean_abs"] = dict(sorted(shap_mean.items(), key=lambda kv: kv[1], reverse=True))

    # Pass 2: pruned feature set → threshold from pooled validation preds.
    kept = prune_features(shap_mean, keep_top=args.keep_top)
    report["pruned_features"] = kept
    fold_stats_pruned, pooled_pruned, _ = run_walk_forward(train, kept)
    report["walk_forward_pruned"] = fold_stats_pruned
    threshold_info = select_threshold(pooled_pruned)
    report["threshold_selection"] = threshold_info
    threshold = float(threshold_info["threshold"])

    # Final model: all train rows, pruned features, median best_iteration rounds.
    import xgboost as xgb

    rounds = int(np.median([f["best_iteration"] for f in fold_stats_pruned]) + 1)
    dtrain = xgb.DMatrix(train[kept].to_numpy(dtype=float), label=train["label"].to_numpy(dtype=int), feature_names=kept)
    final_booster = xgb.train(XGB_PARAMS, dtrain, num_boost_round=max(rounds, 10))

    bundle_dir = Path(args.bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    model_path = bundle_dir / "xgb_filter.json"
    final_booster.save_model(str(model_path))
    (bundle_dir / "filter_meta.json").write_text(
        json.dumps(
            {
                "schema_version": "xgb-filter-meta-v1",
                "trained_at_utc": report["asof_utc"],
                "features": kept,
                "threshold": threshold,
                "train_rows": int(len(train)),
                "train_window_only": True,
                "num_boost_round": max(rounds, 10),
                "params": XGB_PARAMS,
                "status": "research_only_not_promoted",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    report["model_path"] = str(model_path)

    # One-shot holdout evaluation — the only holdout touch, reported verbatim.
    report["one_shot_holdout"] = one_shot_holdout_eval(final_booster, holdout, kept, threshold)

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
