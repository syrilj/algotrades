#!/usr/bin/env python3
"""CLI: anchored walk-forward validation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantmodel.config import load_config
from quantmodel.validation.walkforward import run_walkforward


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: run_walkforward.py <config.yaml>")
        return 2
    cfg = load_config(sys.argv[1])
    out = run_walkforward(cfg)
    print(json.dumps({k: v for k, v in out.items() if k != "folds"}, indent=2))
    print(f"folds: {out.get('n_folds')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
