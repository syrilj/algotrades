#!/usr/bin/env python3
"""Feedback-loop experiment harness (2026-07-11 LSE improvement loops).

Standardizes: scaffold run dir -> backtest -> metrics -> compare vs v15 baseline.

Usage:
  .venv/bin/python runs/poc_va_v20_loops/harness.py \
      --name v20a_riskparity \
      --code-from runs/poc_va_v15/code \
      --window std \
      --config-extra '{"optimizer": "risk_parity"}'

Windows:
  std        2024-08-01..2026-07-11 1H   (winner comparison window)
  long1d     2020-01-01..2026-07-11 1D   (long stress)
  firsthalf  2024-08-01..2025-07-15 1H   (stability split A)
  secondhalf 2025-07-15..2026-07-11 1H   (stability split B)

Baselines (v15_meta_xgb):
  std:    sharpe 2.1280 wr 0.6231 pf 2.6768 dd -0.1324 n 130
  long1d: sharpe 0.7506 wr 0.5641 pf 1.7018 dd -0.2216 n 156
"""
from __future__ import annotations

import argparse
import io
import json
import shutil
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "runs"

WINDOWS = {
    "std": {"start_date": "2024-08-01", "end_date": "2026-07-11", "interval": "1H"},
    "long1d": {"start_date": "2020-01-01", "end_date": "2026-07-11", "interval": "1D"},
    "firsthalf": {"start_date": "2024-08-01", "end_date": "2025-07-15", "interval": "1H"},
    "secondhalf": {"start_date": "2025-07-15", "end_date": "2026-07-11", "interval": "1H"},
}

BASELINE = {
    "std": {"sharpe": 2.1280, "win_rate": 0.6231, "profit_factor": 2.6768, "max_drawdown": -0.1324, "trade_count": 130},
    "long1d": {"sharpe": 0.7506, "win_rate": 0.5641, "profit_factor": 1.7018, "max_drawdown": -0.2216, "trade_count": 156},
}

PASS_BAR = {"profit_factor_min": 1.2, "max_drawdown_max_abs": 0.25, "sharpe_min": 0.5, "min_trades": 40}

DEFAULT_CODES = ["TSLA.US", "ARM.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US"]


def run_one(name: str, code_from: Path, window: str, config_extra: dict, codes: list[str]) -> dict:
    run_dir = RUNS / f"{name}__{window}"
    code_dir = run_dir / "code"
    if code_dir.exists():
        shutil.rmtree(code_dir)
    code_dir.mkdir(parents=True)
    for f in Path(code_from).iterdir():
        if f.is_file():
            shutil.copy2(f, code_dir / f.name)

    cfg = {
        "source": "yfinance",
        "codes": codes,
        "initial_cash": 1000000,
        "commission": 0.001,
        "engine": "daily",
        **WINDOWS[window],
        "strategy": {"model_version": name, "note": f"loop experiment {name} on {window}"},
    }
    cfg.update(config_extra)
    (run_dir / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, "-c",
         "from pathlib import Path; from backtest.runner import main; "
         f"main(Path({str(run_dir)!r}).resolve())"],
        capture_output=True, text=True, timeout=1200,
        env={**__import__('os').environ, "VIBE_TRADING_DATA_CACHE": "1"},
    )
    out = proc.stdout.strip()
    # metrics JSON is the last {...} block on stdout
    start = out.rfind("{")
    # find the outermost JSON object at the end
    depth = 0
    idx = None
    for i in range(len(out) - 1, -1, -1):
        c = out[i]
        if c == "}":
            depth += 1
        elif c == "{":
            depth -= 1
            if depth == 0:
                idx = i
                break
    if idx is None:
        return {"error": "no metrics JSON in output", "stdout_tail": out[-800:], "stderr_tail": proc.stderr[-800:]}
    try:
        metrics = json.loads(out[idx:])
    except json.JSONDecodeError:
        return {"error": "metrics parse failed", "stdout_tail": out[-800:]}
    return metrics


def check_pass_bar(m: dict) -> tuple[bool, list[str]]:
    reasons = []
    if m.get("profit_factor", 0) < PASS_BAR["profit_factor_min"]:
        reasons.append(f"pf {m.get('profit_factor')} < 1.2")
    if abs(m.get("max_drawdown", -1)) > PASS_BAR["max_drawdown_max_abs"]:
        reasons.append(f"|dd| {abs(m.get('max_drawdown', -1)):.3f} > 0.25")
    if m.get("sharpe", 0) < PASS_BAR["sharpe_min"]:
        reasons.append(f"sharpe {m.get('sharpe')} < 0.5")
    if m.get("trade_count", 0) < PASS_BAR["min_trades"]:
        reasons.append(f"n {m.get('trade_count')} < 40")
    return (len(reasons) == 0, reasons)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--code-from", required=True)
    ap.add_argument("--window", default="std", choices=list(WINDOWS))
    ap.add_argument("--config-extra", default="{}")
    ap.add_argument("--codes", default=",".join(DEFAULT_CODES))
    args = ap.parse_args()

    codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    metrics = run_one(args.name, Path(args.code_from), args.window, json.loads(args.config_extra), codes)
    if "error" in metrics:
        print(json.dumps(metrics, indent=2))
        sys.exit(1)

    passed, reasons = check_pass_bar(metrics)
    base = BASELINE.get(args.window)
    summary = {
        "name": args.name,
        "window": args.window,
        "metrics": {k: metrics.get(k) for k in ("sharpe", "win_rate", "profit_factor", "max_drawdown", "trade_count", "total_return", "annual_return", "calmar", "sortino")},
        "pass_bar": {"passed": passed, "reasons": reasons},
    }
    if base:
        summary["vs_v15"] = {
            k: round(float(metrics.get(k, 0)) - base[k], 4) for k in base
        }
        summary["beats_v15_sharpe"] = bool(metrics.get("sharpe", 0) > base["sharpe"])
    run_dir = RUNS / f"{args.name}__{args.window}"
    (run_dir / "loop_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
