#!/usr/bin/env python3
"""Reconcile and freeze the current champion baseline manifest.

Runs the best-known single models (v39b and v39d) under identical
config, data, cost, and cash assumptions, then writes a signed manifest
with engine/data/environment provenance.

Usage:
    .venv/bin/python tools/baseline_manifest.py --cash 1000
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "baseline_manifests"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from evolve.cache import cache_key, data_bundle_hash, engine_bundle_hash, env_versions  # noqa: E402
import dynamic_model_rank as dmr  # noqa: E402
from evolve.experiment_tracking import log_run_from_row  # noqa: E402

CASH = 1_000
WINNER_BAG = ["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "XLP.US", "QQQ.US"]
START = "2024-08-01"
END = "2026-07-11"
TAG = "baseline_manifest_v1"
MODELS = ["v39b_live_adapt", "v39d_confluence"]


def _git_sha() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True)
            .strip()
            [:12]
        )
    except Exception:
        return "unknown"


def _manifest_name() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"baseline_manifest_{ts}.json"


def _run_one(model: dict[str, Any], cash: float) -> dict[str, Any]:
    mode = "daily"
    key = cache_key(
        model,
        mode=mode,
        codes=WINNER_BAG,
        start=START,
        end=END,
        cash=cash,
        interval="1H",
        source="local",
        extra={"tag": TAG, "commission": 0.001, "force_1d": False},
    )
    row = dmr.run_one(
        model,
        mode=mode,
        codes=WINNER_BAG,
        start=START,
        end=END,
        tag=TAG,
        cash=cash,
        force_1d=False,
        source="local",
        interval="1H",
        reuse=False,
    )
    row["cache_key"] = key
    return row


def _attach_provenance(row: dict[str, Any], model: dict[str, Any], cash: float) -> dict[str, Any]:
    row = dict(row)
    row["source"] = "local"
    row["interval"] = "1H"
    row["data_hash"] = data_bundle_hash("local", "1H", WINNER_BAG, START, END)
    row["env_versions"] = env_versions()
    row["provenance"] = {
        "cash": cash,
        "codes": WINNER_BAG,
        "start": START,
        "end": END,
        "source": "local",
        "interval": "1H",
        "engine_hash": engine_bundle_hash(model),
        "data_hash": row["data_hash"],
        "env": row["env_versions"],
        "git_sha": _git_sha(),
        "model_id": model["id"],
    }
    log_run_from_row(model, row)
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cash", type=float, default=CASH)
    args = ap.parse_args()
    cash = float(args.cash)

    os.environ.setdefault("VIBE_TRADING_DATA_CACHE", "1")
    os.environ.setdefault("VIBE_TRADING_DATA_CACHE_ROOT", str(ROOT / "data_cache"))

    models = dmr.discover_models(MODELS)
    by_id = {m["id"]: m for m in models}
    missing = [m for m in MODELS if m not in by_id]
    if missing:
        print(f"Missing models: {missing}")
        return 1

    results: dict[str, Any] = {}
    for mid in MODELS:
        print(f"[baseline] running {mid} @ ${cash:,.0f}")
        row = _run_one(by_id[mid], cash)
        results[mid] = _attach_provenance(row, by_id[mid], cash)

    # Champion = highest OOS total return after identical costs
    ok = [r for r in results.values() if not r.get("error") and r.get("n", 0) > 0]
    champion = max(ok, key=lambda r: float(r.get("ret", -9))) if ok else None

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "cash": cash,
        "codes": WINNER_BAG,
        "start": START,
        "end": END,
        "source": "local",
        "interval": "1H",
        "commission": 0.001,
        "git_sha": _git_sha(),
        "env": env_versions(),
        "champion": champion["id"] if champion else None,
        "champion_ret": champion["ret"] if champion else None,
        "champion_sharpe": champion["sharpe"] if champion else None,
        "champion_dd": champion["dd"] if champion else None,
        "champion_n": champion["n"] if champion else None,
        "results": results,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / _manifest_name()
    path.write_text(json.dumps(manifest, indent=2, default=str))
    print(f"[baseline] wrote {path}")
    print(f"[baseline] champion = {manifest['champion']} ret={manifest['champion_ret']:.3%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
