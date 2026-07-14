#!/usr/bin/env python3
"""Train v44_absorption meta XGB from its own candidate ledger.

Workflow:
  1. Seed a constant XGB (proba=0.5) so v44 can run and generate candidates.
  2. Run v44 to produce run_dir/artifacts/candidates.csv.
  3. Fit a real XGBClassifier on passed candidates (return_pct > 0 label).
  4. Overwrite v44/meta_xgb_final.json and run again for final metrics.

Usage:
  .venv/bin/python tools/train_v44_meta.py --seed --retrain
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models" / "poc_va_macdha" / "v44_absorption"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import dynamic_model_rank as dmr

CODES = ["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "XLP.US", "QQQ.US"]
START = "2024-08-01"
END = "2026-07-11"
CASH = 1_000.0


def _load_meta_cfg() -> dict:
    return json.loads((MODEL_DIR / "meta_config.json").read_text(encoding="utf-8"))


def _seed_xgb(force: bool = False) -> Path:
    """Create a constant seed XGB so v44 can run once and generate candidates."""
    seed_path = MODEL_DIR / "meta_xgb_final.json"
    if seed_path.exists() and not force:
        return seed_path
    cfg = _load_meta_cfg()
    feat_cols = list(cfg["feat_cols"])
    n = len(feat_cols)
    # Constant X matrix: a single, depth-1 tree on constant data cannot split,
    # so it falls back to base_score and outputs ~0.5 for all inputs.
    X = pd.DataFrame(np.zeros((10, n), dtype=float), columns=feat_cols)
    y = np.array([0, 0, 0, 0, 0, 1, 1, 1, 1, 1], dtype=int)
    clf = XGBClassifier(
        n_estimators=1,
        max_depth=1,
        learning_rate=0.1,
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=42,
    )
    clf.fit(X, y)
    clf.save_model(str(seed_path))
    print(f"[seed] wrote {seed_path} ({n} features)")
    return seed_path


def _train_from_candidates(candidates_path: Path) -> None:
    """Train the real meta XGB from a candidate ledger and save it to the model dir."""
    cfg = _load_meta_cfg()
    feat_cols = list(cfg["feat_cols"])
    feat_cols_safe = [f"f_{c.strip().replace(' ', '_').replace('/', '_').replace(':', '_')}" for c in feat_cols]

    df = pd.read_csv(candidates_path)
    passed = df["passed"].astype(int) == 1
    df_pass = df[passed].copy()
    if df_pass.empty:
        raise RuntimeError("No passed candidates in ledger; cannot train.")

    df_pass["return_pct"] = pd.to_numeric(df_pass["return_pct"], errors="coerce")
    df_pass = df_pass.dropna(subset=["return_pct"])
    if df_pass.empty:
        raise RuntimeError("No passed candidates with return_pct; cannot train.")

    X = df_pass[feat_cols_safe].astype(float).values
    y = (df_pass["return_pct"] > 0).astype(int).values

    pos = y.sum()
    neg = len(y) - pos
    scale_pos_weight = float(neg / max(pos, 1)) if pos and neg else 1.0

    clf = XGBClassifier(
        n_estimators=60,
        max_depth=3,
        learning_rate=0.1,
        objective="binary:logistic",
        eval_metric="logloss",
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=2,
        scale_pos_weight=1.0,
        random_state=42,
    )
    clf.fit(X, y)

    out = MODEL_DIR / "meta_xgb_final.json"
    clf.save_model(str(out))
    print(f"[train] fitted XGB on {len(y)} candidates ({pos} wins, {neg} losses) -> {out}")


def _run_model(tag: str) -> dict:
    """Run v44_absorption once and return the dmr row dict."""
    model = dmr.discover_models(["v44_absorption"])[0]
    return dmr.run_one(
        model,
        mode="daily",
        codes=CODES,
        start=START,
        end=END,
        tag=tag,
        cash=CASH,
        force_1d=False,
        source="local",
        interval="1H",
        reuse=False,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Train v44_absorption meta XGB")
    ap.add_argument("--seed", action="store_true", help="write seed XGB before running")
    ap.add_argument("--retrain", action="store_true", help="train real XGB after seed run")
    ap.add_argument("--seed-tag", default="v44_train_seed", help="tag for seed backtest")
    ap.add_argument("--final-tag", default="v44_final", help="tag for final backtest")
    args = ap.parse_args()

    if args.seed:
        _seed_xgb(force=True)

    seed_row = _run_model(args.seed_tag)
    if seed_row.get("error"):
        print(f"[seed] backtest failed: {seed_row['error']}")
        return 1

    run_dir = ROOT / seed_row["path"]
    candidates_csv = run_dir / "artifacts" / "candidates.csv"
    if not candidates_csv.exists():
        print(f"[seed] no candidates ledger at {candidates_csv}")
        return 1

    if not args.retrain:
        print("[seed] done. pass --retrain to fit real XGB.")
        return 0

    _train_from_candidates(candidates_csv)

    final_row = _run_model(args.final_tag)
    if final_row.get("error"):
        print(f"[final] backtest failed: {final_row['error']}")
        return 1

    print(
        f"[final] v44_absorption: ret={final_row['ret']:.3%} "
        f"sharpe={final_row['sharpe']:.3f} dd={final_row['dd']:.3%} "
        f"n={final_row['n']} wr={final_row['wr']:.3%}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
