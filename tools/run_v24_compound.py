#!/usr/bin/env python3
"""Run v24_compound with the state-aware options_portfolio engine.

The installed backtest.engines.options_portfolio does not expose portfolio
state to the SignalEngine. We load a patched version from
tools/backtest_engines/options_portfolio.py that calls
SignalEngine.generate_day(data_map, state, ts) each day, allowing the signal
engine to size using the actual cash and positions.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CUSTOM_OP = ROOT / "tools" / "backtest_engines" / "options_portfolio.py"


def _patch_options_portfolio() -> None:
    spec = importlib.util.spec_from_file_location(
        "backtest.engines.options_portfolio", CUSTOM_OP
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load custom options_portfolio from {CUSTOM_OP}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["backtest.engines.options_portfolio"] = mod
    spec.loader.exec_module(mod)


def main() -> None:
    _patch_options_portfolio()
    from backtest.runner import main as runner_main
    run_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "runs" / "poc_va_v24_compound"
    runner_main(run_dir.resolve())


if __name__ == "__main__":
    main()
