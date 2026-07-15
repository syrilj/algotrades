#!/usr/bin/env python3
"""Fit the fixed-complexity, fold-local v39d causal XGBoost sizing model."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from xgboost import XGBClassifier


META_FEATURES = (
    "dist_poc", "dist_val", "dist_vwap", "ha_green", "above_vwap", "vol_expand",
    "macd_hist", "block_red_flag_on", "htf_green", "atr_pct", "conf", "spy_htf_green",
    "sym_TSLA", "sym_ARM", "sym_MU", "sym_SPY", "sym_IONQ", "sym_APLD",
)


def inverse_concurrency_weight(frame: pd.DataFrame) -> pd.Series:
    starts = pd.to_datetime(frame["timestamp"])
    ends = pd.to_datetime(frame["exit_timestamp"].fillna(frame["timestamp"]))
    weights = []
    for start, end in zip(starts, ends):
        active = ((starts <= start) & (ends >= start)).sum()
        duration = max((end - start).total_seconds(), 1.0)
        weights.append(1.0 / max(int(active), 1) / np.sqrt(duration))
    values = pd.Series(weights, index=frame.index, dtype=float)
    return values / values.mean()


def train(ledger: Path, out_dir: Path, train_end: str, seed: int = 42) -> dict:
    frame = pd.read_csv(ledger)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    frame = frame[(frame["timestamp"] <= pd.Timestamp(train_end)) & (frame["label"].notna())].copy()
    frame["label"] = pd.to_numeric(frame["label"], errors="coerce")
    frame = frame[frame["label"].isin([0, 1])]
    if len(frame) < 50 or frame["label"].nunique() < 2:
        raise ValueError("fold needs at least 50 labelled candidates from both classes")
    columns = [f"f_{feature}" for feature in META_FEATURES]
    for column in columns:
        if column not in frame:
            frame[column] = 0.0
    features = frame[columns].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    weights = inverse_concurrency_weight(frame)
    model = XGBClassifier(
        n_estimators=64,
        max_depth=2,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=10,
        reg_lambda=10.0,
        reg_alpha=1.0,
        objective="binary:logistic",
        eval_metric="logloss",
        n_jobs=1,
        random_state=seed,
    )
    model.fit(features, frame["label"].astype(int), sample_weight=weights)
    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / "meta_xgb_fold.json"
    model.save_model(model_path)
    metadata = {
        "feat_cols": list(META_FEATURES),
        "threshold": 0.50,
        "label": "executed_after_cost_outcome",
        "train_end": str(pd.Timestamp(train_end)),
        "rows": int(len(frame)),
        "positive_rate": float(frame["label"].mean()),
        "seed": seed,
        "params": model.get_params(),
        "artifact": model_path.name,
    }
    (out_dir / "meta_config.json").write_text(json.dumps(metadata, indent=2, sort_keys=True))
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--train-end", required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    print(json.dumps(train(args.ledger, args.out_dir, args.train_end, args.seed), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
