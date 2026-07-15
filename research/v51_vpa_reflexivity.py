#!/usr/bin/env python3
"""Research harness for v51 VPA + reflexivity + meta-labeling.

Run with:
    .venv/bin/python research/v51_vpa_reflexivity.py

Outputs:
    - models/poc_va_macdha/v51_vpa_reflexivity/meta_config.json
    - models/poc_va_macdha/v51_vpa_reflexivity/meta_xgb_final.json
    - models/poc_va_macdha/v51_vpa_reflexivity/hunt_config.json
    - runs/v51_research/REPORT.md
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import precision_score, recall_score, roc_auc_score
from xgboost import XGBClassifier

# Make the v51 feature module importable
ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models" / "poc_va_macdha" / "v51_vpa_reflexivity"
sys.path.insert(0, str(MODEL_DIR))

from features import compute_features, primary_events, triple_barrier_labels  # noqa: E402

warnings.filterwarnings("ignore")

DATA_DIR = ROOT / "data_cache" / "1h"
OUT_DIR = ROOT / "runs" / "v51_research"
OUT_DIR.mkdir(parents=True, exist_ok=True)

UNIVERSE = [c + ".US" for c in ["APLD", "ARM", "COIN", "HYG", "IONQ", "LQD", "MSTR", "MU", "NVDA", "PLTR", "QQQ", "RKLB", "SPY", "TSLA", "XLP"]]
TRAIN_END = "2025-09-30"
VAL_END = "2025-12-31"
TEST_END = "2026-07-11"

PROFIT_MULT = 1.0
LOSS_MULT = 1.0
MAX_HOLD = 5
TARGET_PRECISION = 0.65


def _to_filename(code: str) -> str:
    """TSLA.US -> TSLA.parquet."""
    return code.replace(".US", "").replace(".HK", "") + ".parquet"


def load_data(codes: list[str]) -> dict[str, pd.DataFrame]:
    data_map: dict[str, pd.DataFrame] = {}
    for code in codes:
        path = DATA_DIR / _to_filename(code)
        if not path.exists():
            print(f"[warn] missing data for {code} at {path}")
            continue
        df = pd.read_parquet(path)
        if "date" in df.columns:
            df = df.set_index("date")
        df.index = pd.to_datetime(df.index)
        data_map[code] = df
    return data_map


def build_training_data(
    data_map: dict[str, pd.DataFrame],
    train_end: str,
    val_end: str | None = None,
) -> tuple:
    spy_df = data_map.get("SPY.US")
    all_features: list[pd.DataFrame] = []
    all_labels: list[pd.Series] = []
    event_counts: dict[str, int] = {}
    label_stats: dict[str, int] = {}
    for code, df in data_map.items():
        feats = compute_features(df, spy_df)
        events = primary_events(feats)
        labels, touches, realized = triple_barrier_labels(df, events, PROFIT_MULT, LOSS_MULT, MAX_HOLD)
        event_counts[code] = int(events.sum())
        label_stats[code] = int(labels.dropna().sum())
        # append close/ret_1/date to the feature matrix for bookkeeping
        feats = feats.assign(code=code, ret_1=df["close"].pct_change().fillna(0), date=feats.index)
        all_features.append(feats)
        all_labels.append(labels.to_frame("y").assign(date=labels.index))
        print(
            f"[data] {code}: events={event_counts[code]}, labels=1={label_stats[code]}, "
            f"mean_label={labels.dropna().mean():.3f}"
        )
    full = pd.concat(all_features, ignore_index=True)
    labels_df = pd.concat(all_labels, ignore_index=True)
    # drop rows with any NaN feature
    feat_cols = [c for c in full.columns if c not in {"code", "ret_1", "date"}]
    mask = full[feat_cols].notna().all(axis=1) & labels_df["y"].notna()
    full = full[mask]
    labels_df = labels_df[mask]
    full_dates = pd.to_datetime(full["date"])
    train = full[full_dates <= pd.Timestamp(train_end)]
    train_labels = labels_df.loc[train.index, "y"]
    val = None
    val_labels = None
    if val_end:
        val_mask = (full_dates > pd.Timestamp(train_end)) & (full_dates <= pd.Timestamp(val_end))
        val = full[val_mask]
        val_labels = labels_df.loc[val.index, "y"]
    test_end_ts = pd.Timestamp(val_end) if val_end else pd.Timestamp(train_end)
    test = full[full_dates > test_end_ts]
    test_labels = labels_df.loc[test.index, "y"]
    labels = labels_df["y"]
    return train, train_labels, val, val_labels, test, test_labels, full, labels, feat_cols


def tune_threshold(proba: np.ndarray, y: np.ndarray, target_precision: float = 0.70) -> float:
    """Choose a probability threshold that maximizes precision with a minimum trade count."""
    thresholds = np.linspace(0.30, 0.95, 50)
    best_thr = 0.5
    best_prec = -1.0
    for thr in thresholds:
        pred = (proba[:, 1] >= thr).astype(int)
        if pred.sum() < 10:
            continue
        prec = precision_score(y, pred, zero_division=0)
        # Prefer thresholds that hit target precision, otherwise pick highest precision
        if prec > best_prec:
            best_prec = prec
            best_thr = thr
        if prec >= target_precision and prec >= best_prec:
            best_prec = prec
            best_thr = thr
    return float(best_thr)


def evaluate(name: str, y_true: np.ndarray, proba: np.ndarray, threshold: float) -> dict:
    pred = (proba[:, 1] >= threshold).astype(int)
    n_trades = int(pred.sum())
    if n_trades > 0:
        precision = precision_score(y_true, pred, zero_division=0)
        recall = recall_score(y_true, pred, zero_division=0)
    else:
        precision = recall = 0.0
    try:
        auc = roc_auc_score(y_true, proba[:, 1])
    except Exception:
        auc = float("nan")
    # expectancy using the configured risk/reward multiples
    wins = y_true[pred == 1] == 1
    avg_win = PROFIT_MULT if wins.sum() > 0 else 0.0
    avg_loss = LOSS_MULT
    expectancy = precision * avg_win - (1 - precision) * avg_loss if n_trades > 0 else 0.0
    return {
        "split": name,
        "n_events": int(len(y_true)),
        "n_trades": n_trades,
        "baseline_precision": float(y_true.mean()),
        "precision": float(precision),
        "recall": float(recall),
        "auc": float(auc),
        "expectancy_R": float(expectancy),
        "threshold": float(threshold),
    }


def main() -> None:
    print("=" * 60)
    print("v51 VPA + reflexivity + meta-labeling research")
    print("=" * 60)

    data_map = load_data(UNIVERSE)
    if not data_map:
        raise RuntimeError("No data loaded")

    train, train_labels, val, val_labels, test, test_labels, full, labels, feat_cols = build_training_data(
        data_map, TRAIN_END, VAL_END
    )

    print(f"\n[split] train={len(train)} events, val={len(val) if val is not None else 0}, test={len(test)}")

    X_train = train[feat_cols].to_numpy(dtype=float)
    y_train = train_labels.to_numpy(dtype=float)
    X_val = val[feat_cols].to_numpy(dtype=float) if val is not None else None
    y_val = val_labels.to_numpy(dtype=float) if val_labels is not None else None
    X_test = test[feat_cols].to_numpy(dtype=float)
    y_test = test_labels.to_numpy(dtype=float)

    scale_pos_weight = float((y_train == 0).sum() / max(1, (y_train == 1).sum()))
    print(f"[train] class imbalance: pos={(y_train==1).sum()}, neg={(y_train==0).sum()}, scale={scale_pos_weight:.2f}")

    model = XGBClassifier(
        n_estimators=80,
        max_depth=2,
        learning_rate=0.05,
        subsample=0.6,
        colsample_bytree=0.6,
        scale_pos_weight=1.0,
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=42,
        n_jobs=4,
        reg_alpha=1.0,
        reg_lambda=5.0,
        min_child_weight=50,
    )
    model.fit(X_train, y_train)

    train_proba = model.predict_proba(X_train)
    val_proba = model.predict_proba(X_val) if X_val is not None else None
    test_proba = model.predict_proba(X_test)

    # Threshold tuning on validation, or on train if no validation
    if val_proba is not None:
        threshold = tune_threshold(val_proba, y_val, TARGET_PRECISION)
    else:
        threshold = tune_threshold(train_proba, y_train, TARGET_PRECISION)

    print(f"\n[threshold] selected p >= {threshold:.3f}")

    results = [
        evaluate("train", y_train, train_proba, threshold),
    ]
    if val_proba is not None:
        results.append(evaluate("val", y_val, val_proba, threshold))
    results.append(evaluate("test", y_test, test_proba, threshold))

    for r in results:
        print(f"\n[{r['split']}]")
        for k, v in r.items():
            print(f"  {k}: {v}")

    # Save artifacts
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model.save_model(str(MODEL_DIR / "meta_xgb_final.json"))
    meta_cfg = {
        "feat_cols": feat_cols,
        "threshold": threshold,
        "profit_mult": PROFIT_MULT,
        "loss_mult": LOSS_MULT,
        "max_hold": MAX_HOLD,
        "target_precision": TARGET_PRECISION,
        "train_end": TRAIN_END,
        "val_end": VAL_END,
        "test_end": TEST_END,
        "universe": UNIVERSE,
        "scale_pos_weight": scale_pos_weight,
    }
    (MODEL_DIR / "meta_config.json").write_text(json.dumps(meta_cfg, indent=2, default=str))

    # Feature importances
    importance = pd.Series(model.feature_importances_, index=feat_cols).sort_values(ascending=False)
    print("\n[top features]")
    print(importance.head(15).to_string())

    # Write report
    report = {
        "meta_config": meta_cfg,
        "results": results,
        "feature_importance": importance.to_dict(),
    }
    (OUT_DIR / "REPORT.json").write_text(json.dumps(report, indent=2, default=str))
    md = f"""# v51 VPA + Reflexivity Research Report

## Config

```json
{json.dumps(meta_cfg, indent=2, default=str)}
```

## Results

```json
{json.dumps(results, indent=2, default=str)}
```

## Top Features

```
{importance.head(15).to_string()}
```
"""
    (OUT_DIR / "REPORT.md").write_text(md)
    print(f"\n[done] model saved to {MODEL_DIR}; report to {OUT_DIR}")


if __name__ == "__main__":
    main()
