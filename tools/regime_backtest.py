#!/usr/bin/env python3
"""Multi-regime daily-bar probe for the promoted v72 book (P0-1).

Runs v72_dual_sleeve on 2018+ **daily** bars from ``data_cache/1d`` — fully
offline. The 1H history the promoted contract uses only exists from 2024-07,
so this is a *regime probe* of the rule DNA on 1D bars (the ``v13_long_oos``
pattern), not a like-for-like re-run of the promoted contract. Results are
sliced into the plan's mandatory stress sub-windows (2018 Q4, 2020 Feb–Apr,
2022 full year) and compared against the live kill-switch drawdown levels
from ``tools/risk_manager.py`` (halt_new 18%, flatten 28%).

Data path: ``source="local"`` normally resolves symbols through
``~/.vibe-trading/data-bridge/config.yaml`` (pinned to 1h parquets). This
tool instead patches the local loader to read
``data_cache/1d/<SYM>.parquet`` directly, without touching that user config.

Usage:
  .venv/bin/python tools/regime_backtest.py
  .venv/bin/python tools/regime_backtest.py --start 2018-01-01 --end 2026-07-11
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
os.environ.setdefault("VIBE_TRADING_ALLOWED_RUN_ROOTS", str(ROOT / "runs"))

REGIME_CONFIG_PATH = ROOT / "models" / "poc_va_macdha" / "v72_dual_sleeve" / "regime_stress_config.json"
BUNDLE_DIR = ROOT / "models" / "poc_va_macdha" / "v72_dual_sleeve"
RUN_DIR = ROOT / "runs" / "v72_regime_probe"
DAILY_CACHE = ROOT / "data_cache" / "1d"

# Live kill-switch levels (tools/risk_manager.py default policy).
HALT_NEW_DD = 0.18
FLATTEN_DD = 0.28


def _install_daily_cache_loader() -> None:
    """Point the ``local`` source at data_cache/1d parquets (offline, no user-config edits)."""
    import pandas as pd
    import backtest.loaders.local_loader as local_loader

    def fetch_1d(self, codes, start_date, end_date, fields=None, interval="1D"):  # noqa: ANN001
        out = {}
        for code in codes:
            sym = str(code).replace(".US", "")
            path = DAILY_CACHE / f"{sym}.parquet"
            if not path.exists():
                continue  # fail closed: listing gaps simply have no bars
            frame = pd.read_parquet(path).sort_index()
            frame.index = pd.to_datetime(frame.index)
            if start_date:
                frame = frame[frame.index >= pd.Timestamp(start_date)]
            if end_date:
                frame = frame[frame.index <= pd.Timestamp(end_date)]
            frame.columns = [c.lower() for c in frame.columns]
            out[code] = frame
        return out

    local_loader.DataLoader.fetch = fetch_1d


def slice_sub_windows(equity_csv: Path, sub_windows: dict[str, list[str]]) -> dict[str, Any]:
    """Per-window return / within-window max DD / activity from the equity curve."""
    import pandas as pd

    frame = pd.read_csv(equity_csv, parse_dates=["timestamp"]).set_index("timestamp")
    out: dict[str, Any] = {}
    for name, (start, end) in sub_windows.items():
        window = frame.loc[str(start): str(end)]
        if window.empty:
            out[name] = {"error": "no_bars_in_window"}
            continue
        equity = window["equity"]
        drawdown = float((equity / equity.cummax() - 1.0).min())
        out[name] = {
            "start": str(start),
            "end": str(end),
            "ret": round(float(equity.iloc[-1] / equity.iloc[0] - 1.0), 4),
            "max_dd_within": round(drawdown, 4),
            "frac_bars_active": round(float((window["ret"].abs() > 1e-12).mean()), 3),
            "dd_inside_halt_new": bool(abs(drawdown) < HALT_NEW_DD),
            "dd_inside_flatten": bool(abs(drawdown) < FLATTEN_DD),
        }
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Multi-regime 1D probe for v72_dual_sleeve")
    parser.add_argument("--config", default=str(REGIME_CONFIG_PATH))
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    args = parser.parse_args(argv)

    regime_cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    start = args.start or regime_cfg["start_date"]
    end = args.end or regime_cfg["end_date"]

    import dynamic_model_rank as _dmr  # noqa: F401  local-source runner patches
    _install_daily_cache_loader()
    from backtest.runner import main as bt_main

    if RUN_DIR.exists():
        shutil.rmtree(RUN_DIR)
    code_dir = RUN_DIR / "code"
    code_dir.mkdir(parents=True, exist_ok=True)
    for name in ("signal_engine.py", "hunt_config.json"):
        src = BUNDLE_DIR / name
        if src.exists():
            shutil.copy2(src, code_dir / name)
    (RUN_DIR / "config.json").write_text(
        json.dumps(
            {
                "source": "local",
                "codes": list(regime_cfg["codes"]),
                "start_date": start,
                "end_date": end,
                "initial_cash": regime_cfg.get("initial_cash", 1000),
                "commission": 0.001,
                "engine": "daily",
                "interval": "1D",
                "strategy": {"model_version": "v72_dual_sleeve", "mode": "regime_probe"},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"[regime] RUN v72_dual_sleeve 1D {start}→{end}", flush=True)
    try:
        bt_main(RUN_DIR.resolve())
    except SystemExit as se:
        print(json.dumps({"error": f"backtest SystemExit: {se}"}))
        return 2

    metrics_path = RUN_DIR / "artifacts" / "metrics.csv"
    with metrics_path.open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    for p in (RUN_DIR / "artifacts").glob("ohlcv_*.csv"):
        p.unlink(missing_ok=True)

    sub = slice_sub_windows(RUN_DIR / "artifacts" / "equity.csv", regime_cfg["sub_windows"])
    report = {
        "schema_version": "regime-probe-v1",
        "asof_utc": datetime.now(timezone.utc).isoformat(),
        "model": "v72_dual_sleeve",
        "caveat": (
            "1D-bar probe of the rule DNA; the promoted contract is 1H. Kill-switch throttles "
            "(halt_new/flatten) are NOT simulated inside this backtest — a live book would have "
            "reduced or halted risk before reaching the raw drawdowns shown here."
        ),
        "window": {"start": start, "end": end},
        "full_run": {
            "ret": float(row["total_return"]),
            "dd": float(row["max_drawdown"]),
            "sharpe": float(row["sharpe"]),
            "n": int(float(row["trade_count"])),
            "wr": float(row["win_rate"]),
        },
        "kill_switch_levels": {"halt_new_dd": HALT_NEW_DD, "flatten_dd": FLATTEN_DD},
        "sub_windows": sub,
        "run_dir": str(RUN_DIR.relative_to(ROOT)),
    }
    out_path = RUN_DIR / "RESULTS.json"
    out_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
