#!/usr/bin/env python3
"""Train v60_microstructure XGB meta-classifier from triple-barrier labels.

Usage:
  .venv/bin/python tools/train_v60_microstructure.py --retrain

Workflow:
  1. Fetch source=local 1H OHLCV for the WINNER bag.
  2. Compute point-in-time microstructure features per symbol.
  3. Label each bar with a triple-barrier outcome (entry at next bar open).
  4. Train an XGBClassifier on the combined sample.
  5. Save models/poc_va_macdha/v60_microstructure/meta_xgb_final.json.
  6. Enable use_xgb in the model's hunt_config.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import importlib.util

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models" / "poc_va_macdha" / "v60_microstructure"

# Load the engine module for its feature helpers.
# Do not instantiate SignalEngine to avoid touching the (possibly missing) booster.
engine_spec = importlib.util.spec_from_file_location(
    "v60_engine", str(MODEL_DIR / "signal_engine.py")
)
engine_mod = importlib.util.module_from_spec(engine_spec)
engine_spec.loader.exec_module(engine_mod)

compute_feature_df = engine_mod.compute_feature_df

from backtest.loaders.registry import get_loader_cls_with_fallback
from xgboost import XGBClassifier

CODES = ["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "XLP.US", "QQQ.US"]
START = "2024-08-01"
END = "2026-07-11"
INTERVAL = "1H"
SOURCE = "local"


def _load_hunt_config() -> dict:
    path = MODEL_DIR / "hunt_config.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _load_meta_config() -> dict:
    path = MODEL_DIR / "meta_config.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _triple_barrier_label(
    df: pd.DataFrame,
    features: pd.DataFrame,
    sl_mult: float,
    tp_mult: float,
    max_hold: int,
) -> pd.Series:
    """Compute point-in-time triple-barrier labels for each bar.

    Entry is assumed at the next bar's open. The SL/TP are anchored to the ATR
    observed at the current bar (no future leakage). Label is 1 if the upper
    barrier is touched before the lower barrier, else 0.
    """
    close = df["close"].astype(float)
    open_ = df["open"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    atr_pct = features["atr_pct"].astype(float)

    n = len(df)
    labels = np.zeros(n, dtype=int)
    for t in range(n - 1):
        entry = open_.iloc[t + 1]
        if entry <= 0 or pd.isna(entry):
            continue
        atr = atr_pct.iloc[t] * close.iloc[t]
        if atr <= 0 or pd.isna(atr):
            continue
        sl = entry - max(0.005, sl_mult * atr)
        tp = entry + max(0.010, tp_mult * atr)
        end = min(t + 1 + max_hold, n)
        label = 0
        for i in range(t + 1, end):
            bar_low = low.iloc[i]
            bar_high = high.iloc[i]
            if bar_low <= sl and bar_high >= tp:
                # Both touched in same bar; use intrabar direction proxy
                if close.iloc[i] > open_.iloc[i]:
                    label = 1
                else:
                    label = 0
                break
            if bar_low <= sl:
                label = 0
                break
            if bar_high >= tp:
                label = 1
                break
        else:
            # No barrier touched by max hold; use final sign
            final_close = close.iloc[end - 1]
            label = 1 if final_close > entry else 0
        labels[t] = label
    return pd.Series(labels, index=df.index)


def _train_xgb(X: pd.DataFrame, y: np.ndarray, feat_cols: list[str]) -> XGBClassifier:
    pos = y.sum()
    neg = len(y) - pos
    scale_pos_weight = float(neg / max(pos, 1)) if pos and neg else 1.0

    clf = XGBClassifier(
        n_estimators=80,
        max_depth=3,
        learning_rate=0.05,
        objective="binary:logistic",
        eval_metric="logloss",
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=3,
        scale_pos_weight=scale_pos_weight,
        random_state=42,
    )
    clf.fit(X[feat_cols].astype(float), y)
    return clf


def main() -> int:
    ap = argparse.ArgumentParser(description="Train v60_microstructure XGB")
    ap.add_argument("--retrain", action="store_true", help="train and overwrite model")
    ap.add_argument("--start", default=START, help="training start date")
    ap.add_argument("--end", default=END, help="training end date")
    ap.add_argument("--source", default=SOURCE, help="data source")
    ap.add_argument("--interval", default=INTERVAL, help="bar interval")
    args = ap.parse_args()

    hunt = _load_hunt_config()
    meta = _load_meta_config()
    feat_cols = list(meta.get("feat_cols", []))
    if not feat_cols:
        print("[train] no feat_cols in meta_config.json")
        return 1

    sl_mult = float(hunt.get("sl_atr_mult", 1.5))
    tp_mult = float(hunt.get("tp_atr_mult", 3.0))
    max_hold = int(hunt.get("max_hold_bars", 20))

    loader = get_loader_cls_with_fallback(args.source)()
    data_map = loader.fetch(CODES, args.start, args.end, interval=args.interval)
    if not data_map:
        print("[train] no data fetched")
        return 1

    X_rows: list[pd.DataFrame] = []
    y_rows: list[np.ndarray] = []
    for code, df in data_map.items():
        if df is None or df.empty:
            continue
        print(f"[train] processing {code}: {len(df)} bars")
        features = compute_feature_df(df, hunt)
        labels = _triple_barrier_label(df, features, sl_mult, tp_mult, max_hold)
        # Drop the last max_hold rows so labels are not truncated by the end of data.
        if len(df) > max_hold:
            features = features.iloc[:-max_hold]
            labels = labels.iloc[:-max_hold]
        X_rows.append(features[feat_cols])
        y_rows.append(labels.values)

    X = pd.concat(X_rows, ignore_index=True)
    y = np.concatenate(y_rows)

    keep = X.isnull().sum(axis=1) == 0
    X = X[keep]
    y = y[keep]

    if len(y) == 0:
        print("[train] no training rows")
        return 1

    pos = int(y.sum())
    neg = int(len(y) - pos)
    print(f"[train] {len(y)} rows | pos={pos} neg={neg} baseline={pos/max(len(y),1):.3%}")

    if not args.retrain:
        print("[train] dry run. pass --retrain to fit and save model.")
        return 0

    clf = _train_xgb(X, y, feat_cols)
    out = MODEL_DIR / "meta_xgb_final.json"
    clf.save_model(str(out))
    print(f"[train] saved XGB to {out}")

    # Enable XGB in hunt_config
    hunt_path = MODEL_DIR / "hunt_config.json"
    hunt["use_xgb"] = True
    hunt_path.write_text(json.dumps(hunt, indent=2))
    print("[train] set use_xgb=true in hunt_config.json")

    return 0


if __name__ == "__main__":
    sys.exit(main())
