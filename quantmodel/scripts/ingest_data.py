#!/usr/bin/env python3
"""Validate and summarize configured data vendor (no download in v0.1)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantmodel.config import load_config
from quantmodel.data.loader import load_market_data


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: ingest_data.py <config.yaml>")
        return 2
    cfg = load_config(sys.argv[1])
    data = load_market_data(cfg, run_id="ingest")
    meta = data["metadata"]
    bars = data["bars"]
    print("vendor:", meta.get("vendor"))
    print("symbols:", meta.get("symbols"))
    print("n_bars:", len(bars))
    print("n_securities:", meta.get("n_securities"))
    print("data_manifest_hash:", meta.get("data_manifest_hash"))
    print("survivorship_bias:", meta.get("survivorship_bias"))
    print("issues:", len(data["issues"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
