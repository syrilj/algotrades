#!/usr/bin/env python3
"""Train secondary logistic meta-labeler for v61_meta_ledger.

Fits ONLY on the train window ledger from a v39d_confluence run.
Writes models/poc_va_macdha/v61_meta_ledger/secondary_meta.json

Usage:
  .venv/bin/python tools/train_v61_meta_ledger.py --cash 1000 \\
      --train-start 2024-08-01 --train-end 2025-08-01
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "tools"))
import dynamic_model_rank as dmr

MODELS = ROOT / "models" / "poc_va_macdha"
OUT_MODEL = MODELS / "v61_meta_ledger"
BAG = [
    "TSLA.US",
    "MU.US",
    "SPY.US",
    "IONQ.US",
    "APLD.US",
    "XLP.US",
    "QQQ.US",
]


def _find_candidates_csv(run_path: str | Path) -> Path | None:
    p = ROOT / run_path if not Path(run_path).is_absolute() else Path(run_path)
    cand = p / "artifacts" / "candidates.csv"
    if cand.exists():
        return cand
    # Sometimes ledger writes to parent of code/
    alt = p / "candidates.csv"
    return alt if alt.exists() else None


def _load_xy(cand_path: Path) -> tuple[np.ndarray, np.ndarray, list[str]]:
    with cand_path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise RuntimeError(f"empty ledger: {cand_path}")

    f_cols = [c for c in rows[0].keys() if c.startswith("f_")]
    feat_cols = f_cols + ["meta_proba", "adj_proba"]
    xs: list[list[float]] = []
    ys: list[float] = []
    for r in rows:
        # only passed candidates with labels
        try:
            passed = int(float(r.get("passed") or 0))
        except Exception:
            passed = 0
        lab = r.get("label", "")
        if lab in ("", None):
            continue
        try:
            y = int(float(lab))
        except Exception:
            continue
        if y not in (0, 1):
            continue
        if passed != 1:
            # still allow rejected candidates if labeled; prefer passed
            continue
        vec = []
        ok = True
        for c in feat_cols:
            try:
                vec.append(float(r.get(c) if r.get(c) not in ("", None) else 0.0))
            except Exception:
                ok = False
                break
        if not ok:
            continue
        xs.append(vec)
        ys.append(float(y))
    if len(xs) < 20:
        raise RuntimeError(f"too few labeled passed candidates: {len(xs)} in {cand_path}")
    return np.asarray(xs, dtype=float), np.asarray(ys, dtype=float), feat_cols


def _fit_logistic(X: np.ndarray, y: np.ndarray, max_iter: int = 400, lr: float = 0.1, l2: float = 1.0):
    """Minimal L2 logistic (no sklearn required)."""
    mean = X.mean(axis=0)
    scale = X.std(axis=0)
    scale = np.where(scale < 1e-12, 1.0, scale)
    Z = (X - mean) / scale
    n, d = Z.shape
    w = np.zeros(d, dtype=float)
    b = 0.0
    for _ in range(max_iter):
        logits = Z @ w + b
        # stable sigmoid
        p = 1.0 / (1.0 + np.exp(-np.clip(logits, -30, 30)))
        err = p - y
        grad_w = (Z.T @ err) / n + l2 * w
        grad_b = float(err.mean())
        w -= lr * grad_w
        b -= lr * grad_b
    # train accuracy / lift check
    logits = Z @ w + b
    p = 1.0 / (1.0 + np.exp(-np.clip(logits, -30, 30)))
    pred = (p >= 0.5).astype(float)
    acc = float((pred == y).mean())
    base = float(max(y.mean(), 1.0 - y.mean()))
    return w, b, mean, scale, acc, base


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cash", type=float, default=1000.0)
    ap.add_argument("--train-start", default="2024-08-01")
    ap.add_argument("--train-end", default="2025-08-01")
    ap.add_argument("--p-skip", type=float, default=0.45)
    ap.add_argument("--p-full", type=float, default=0.65)
    args = ap.parse_args()

    models = dmr.discover_models(only=["v39d_confluence"])
    if not models:
        raise SystemExit("v39d_confluence not found")
    m = models[0]
    print(
        f"[train-v61] run v39d train window {args.train_start}→{args.train_end}",
        flush=True,
    )
    row = dmr.run_one(
        m,
        mode="daily",
        codes=BAG,
        start=args.train_start,
        end=args.train_end,
        tag="v61_ledger_train",
        force_1d=False,
        reuse=True,
        cash=float(args.cash),
        source="local",
        interval="1H",
    )
    if row.get("error"):
        raise SystemExit(f"train run failed: {row['error']}")
    cand = _find_candidates_csv(row["path"])
    if cand is None:
        # ledger may have written under models/poc_va_macdha/artifacts when
        # run from source; also check model parent after copy path.
        run_dir = ROOT / row["path"]
        # When code is in run_dir/code, ledger uses model_dir.parent = run_dir
        cand = run_dir / "artifacts" / "candidates.csv"
        if not cand.exists():
            # fallback: shared artifacts
            alt = MODELS / "artifacts" / "candidates.csv"
            cand = alt if alt.exists() else None
    if cand is None or not cand.exists():
        raise SystemExit(
            f"candidates.csv not found for run {row.get('path')}. "
            "Ensure CandidateLedger flushes during generate()."
        )
    print(f"[train-v61] ledger={cand} n_run={row.get('n')}", flush=True)
    X, y, feat_cols = _load_xy(cand)
    w, b, mean, scale, acc, base = _fit_logistic(X, y)
    print(
        f"[train-v61] samples={len(y)} pos_rate={y.mean():.3f} "
        f"train_acc={acc:.3f} majority_base={base:.3f}",
        flush=True,
    )
    if acc < base + 0.01:
        print(
            "[train-v61] WARN: train accuracy ~ majority baseline; "
            "secondary may be noise (still writing artifact for campaign fail path)",
            flush=True,
        )

    OUT_MODEL.mkdir(parents=True, exist_ok=True)
    art = {
        "feat_cols": feat_cols,
        "coef": w.tolist(),
        "intercept": float(b),
        "mean": mean.tolist(),
        "scale": scale.tolist(),
        "p_skip": float(args.p_skip),
        "p_full": float(args.p_full),
        "train_start": args.train_start,
        "train_end": args.train_end,
        "n_samples": int(len(y)),
        "pos_rate": float(y.mean()),
        "train_acc": acc,
        "majority_base": base,
        "source_ledger": str(cand),
    }
    out_path = OUT_MODEL / "secondary_meta.json"
    out_path.write_text(json.dumps(art, indent=2), encoding="utf-8")
    # Ensure dmr copies secondary artifact
    dep = {
        "files": [
            {"source": "secondary_meta.json", "target": "secondary_meta.json"},
        ]
    }
    # Also keep shared ledger available
    shared = MODELS / "_shared" / "candidate_ledger.py"
    if shared.exists() and not (OUT_MODEL / "candidate_ledger.py").exists():
        import shutil

        shutil.copy2(shared, OUT_MODEL / "candidate_ledger.py")
    print(f"[train-v61] wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
