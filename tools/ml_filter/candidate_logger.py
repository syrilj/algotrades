#!/usr/bin/env python3
"""Dump rule-generated v72 entry candidates with features + forward labels.

For every symbol in the deployment universe, runs the frozen v72_dual_sleeve
engine over local 1H bars and emits one row per *entry candidate* — a bar
where the engine's target weight transitions from flat to long. Labels use
the engine's own fill convention (open of the next bar) and the actual rule
exit (weight back to flat, filled at the open after the exit bar):

  realized_return = exit_fill / entry_fill - 1 - cost_buffer
  label = 1 if realized_return > 0 else 0

Candidates whose exit is not observed inside the data (still open at the end)
are dropped — fail closed, no imputed outcomes.

Rows are tagged ``window`` = train / holdout / other using the locked windows
from DEPLOYMENT_MANIFEST.json. Only the trainer decides what to fit on; this
logger is deterministic feature/label extraction and fits nothing.

Usage:
  .venv/bin/python tools/ml_filter/candidate_logger.py
  .venv/bin/python tools/ml_filter/candidate_logger.py --output runs/v88_xgb_filter/candidates.csv
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from ml_filter.features import FEATURE_COLUMNS, compute_feature_frame  # noqa: E402

MANIFEST_PATH = ROOT / "models" / "poc_va_macdha" / "DEPLOYMENT_MANIFEST.json"
ENGINE_PATH = ROOT / "models" / "poc_va_macdha" / "v72_dual_sleeve" / "signal_engine.py"
DAILY_CACHE_1H = ROOT / "data_cache" / "1h"
DEFAULT_OUTPUT = ROOT / "runs" / "v88_xgb_filter" / "candidates.csv"

# Round-trip cost buffer: 5 bps slippage per side (promotion cost model) plus
# a 5 bps safety margin — a candidate must beat this to count as a win.
COST_BUFFER = 0.0015


def load_engine(engine_path: Path = ENGINE_PATH) -> Any:
    spec = importlib.util.spec_from_file_location("v88_candidate_source_engine", engine_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.SignalEngine()


def load_bars(symbol: str, start: str, end: str, cache_dir: Path = DAILY_CACHE_1H) -> pd.DataFrame | None:
    path = cache_dir / f"{symbol.replace('.US', '')}.parquet"
    if not path.exists():
        return None
    frame = pd.read_parquet(path).sort_index()
    frame.index = pd.to_datetime(frame.index)
    frame.columns = [c.lower() for c in frame.columns]
    frame = frame[(frame.index >= pd.Timestamp(start)) & (frame.index <= pd.Timestamp(end))]
    return frame if not frame.empty else None


def extract_candidates(
    weights: pd.Series,
    frame: pd.DataFrame,
    features: pd.DataFrame,
    *,
    symbol: str,
    cost_buffer: float = COST_BUFFER,
) -> list[dict[str, Any]]:
    """One row per flat→long transition, labeled by the rule's own exit.

    Fill convention: entry at open[t+1], exit at open[e+1] where ``e`` is the
    first bar after ``t`` whose weight is flat. Candidates without both fills
    inside the data are dropped (fail closed).
    """
    w = weights.reindex(frame.index).fillna(0.0).astype(float).to_numpy()
    opens = frame["open"].astype(float).to_numpy()
    n = len(w)
    rows: list[dict[str, Any]] = []
    long_now = w > 1e-9
    for t in range(1, n - 1):
        if not long_now[t] or long_now[t - 1]:
            continue  # not a fresh entry
        exit_bar = None
        for e in range(t + 1, n):
            if not long_now[e]:
                exit_bar = e
                break
        if exit_bar is None or exit_bar + 1 >= n:
            continue  # still open / exit fill unobservable — drop
        entry_fill = opens[t + 1]
        exit_fill = opens[exit_bar + 1]
        if not (np.isfinite(entry_fill) and entry_fill > 0 and np.isfinite(exit_fill)):
            continue
        realized = exit_fill / entry_fill - 1.0 - cost_buffer
        feat_row = features.iloc[t]
        if feat_row.isna().any():
            continue  # warmup bars without full features — drop, never impute
        rows.append(
            {
                "symbol": symbol,
                "entry_ts": frame.index[t].isoformat(),
                "exit_ts": frame.index[exit_bar].isoformat(),
                "holding_bars": int(exit_bar - t),
                "entry_fill": float(entry_fill),
                "exit_fill": float(exit_fill),
                "realized_return": float(realized),
                "label": 1 if realized > 0 else 0,
                **{k: float(feat_row[k]) for k in FEATURE_COLUMNS},
            }
        )
    return rows


def tag_window(entry_ts: str, contract: dict[str, Any]) -> str:
    ts = pd.Timestamp(entry_ts)
    t0, t1 = (pd.Timestamp(x) for x in contract["train_window"])
    h0, h1 = (pd.Timestamp(x) for x in contract["locked_holdout_window"])
    if h1 == h1.normalize():
        # Date-only holdout end is inclusive of that full trading day.
        h1 = h1 + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    if t0 <= ts < t1:
        return "train"
    if h0 <= ts <= h1:
        return "holdout"
    return "other"


def build_candidates(
    *,
    manifest_path: Path = MANIFEST_PATH,
    engine_path: Path = ENGINE_PATH,
    cache_dir: Path = DAILY_CACHE_1H,
) -> pd.DataFrame:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    contract = manifest["data_contract"]
    start = contract["train_window"][0]
    end = contract["locked_holdout_window"][1]
    universe = list(contract["universe"])

    data_map: dict[str, pd.DataFrame] = {}
    for code in universe:
        frame = load_bars(code, start, end, cache_dir)
        if frame is not None:
            data_map[code] = frame
    if not data_map:
        raise RuntimeError(f"no local 1H bars found under {cache_dir}")

    engine = load_engine(engine_path)
    signals = engine.generate(data_map)
    conf_map = getattr(engine, "last_confidence", {}) or {}
    sleeve_map = getattr(engine, "last_sleeve", {}) or {}
    spy_close = data_map.get("SPY.US", pd.DataFrame()).get("close")

    all_rows: list[dict[str, Any]] = []
    for code, frame in data_map.items():
        weights = signals.get(code)
        if weights is None:
            continue
        features = compute_feature_frame(
            frame,
            symbol=code,
            engine_conf=conf_map.get(code),
            sleeve=sleeve_map.get(code),
            spy_close=spy_close,
        )
        all_rows.extend(extract_candidates(weights, frame, features, symbol=code))

    table = pd.DataFrame(all_rows)
    if table.empty:
        return table
    table["window"] = [tag_window(ts, contract) for ts in table["entry_ts"]]
    return table.sort_values("entry_ts").reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Log v72 entry candidates with features + forward labels")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)

    table = build_candidates()
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out_path, index=False)
    summary = {
        "asof_utc": datetime.now(timezone.utc).isoformat(),
        "output": str(out_path),
        "rows": int(len(table)),
        "by_window": table["window"].value_counts().to_dict() if not table.empty else {},
        "base_rate": float(table["label"].mean()) if not table.empty else None,
        "cost_buffer": COST_BUFFER,
    }
    (out_path.with_suffix(".meta.json")).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
