#!/usr/bin/env python3
"""v25 feedback harness — size mult learning from closed-trade journal (CSV).

Does NOT retune primary side rules. Only reports / suggests feedback mult
and writes a journal summary for the operator.

CSV columns (min): ts, symbol, vehicle, pnl_pct, mode
  vehicle: equity|options
  pnl_pct: e.g. 0.15 or -0.30

Usage:
  python3 models/poc_va_macdha/v25_regime_grow/feedback_loop.py --journal path.csv
  python3 models/poc_va_macdha/v25_regime_grow/feedback_loop.py --demo
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
from risk_manager import feedback_size_mult, load_policy  # noqa: E402


def summarize(journal: pd.DataFrame, pol: dict) -> dict:
    j = journal.copy()
    j["pnl_pct"] = pd.to_numeric(j["pnl_pct"], errors="coerce")
    j = j.dropna(subset=["pnl_pct"]).sort_values("ts")
    history = j["pnl_pct"].astype(float).tolist()
    mult = feedback_size_mult(history, pol)
    wins = sum(1 for x in history if x > 0)
    n = len(history)
    by_v = {}
    if "vehicle" in j.columns:
        for v, g in j.groupby("vehicle"):
            gp = g["pnl_pct"].astype(float)
            by_v[str(v)] = {
                "n": int(len(gp)),
                "wr": float((gp > 0).mean()) if len(gp) else 0.0,
                "avg_pnl_pct": float(gp.mean()) if len(gp) else 0.0,
                "sum_pnl_pct": float(gp.sum()) if len(gp) else 0.0,
            }
    # simple path: start 1000, compound on pnl_pct (equity-style; options approximate)
    eq = 1000.0
    peak = eq
    max_dd = 0.0
    for p in history:
        eq *= 1.0 + float(p) * 0.5  # half-apply: options not full book each time
        peak = max(peak, eq)
        max_dd = min(max_dd, eq / peak - 1.0)
    return {
        "n_trades": n,
        "win_rate": wins / n if n else 0.0,
        "next_feedback_mult": mult,
        "by_vehicle": by_v,
        "path_start": 1000.0,
        "path_end_approx": round(eq, 2),
        "path_max_dd_approx": round(max_dd, 4),
        "policy": pol.get("version"),
        "note": "path_end_approx is a rough journal compound, not a full portfolio backtest",
    }


def demo_journal() -> pd.DataFrame:
    rows = [
        {"ts": "2026-01-02", "symbol": "APLD", "vehicle": "options", "pnl_pct": 0.45, "mode": "OPTIONS_ATTACK"},
        {"ts": "2026-01-08", "symbol": "IONQ", "vehicle": "equity", "pnl_pct": 0.04, "mode": "EQUITY_HEDGE"},
        {"ts": "2026-01-15", "symbol": "APLD", "vehicle": "options", "pnl_pct": -0.30, "mode": "OPTIONS_ATTACK"},
        {"ts": "2026-01-20", "symbol": "MU", "vehicle": "equity", "pnl_pct": 0.02, "mode": "EQUITY_HEDGE"},
        {"ts": "2026-02-01", "symbol": "IONQ", "vehicle": "options", "pnl_pct": 0.55, "mode": "OPTIONS_ATTACK"},
        {"ts": "2026-02-10", "symbol": "APLD", "vehicle": "options", "pnl_pct": 0.40, "mode": "OPTIONS_ATTACK"},
        {"ts": "2026-02-18", "symbol": "IONQ", "vehicle": "options", "pnl_pct": 0.20, "mode": "OPTIONS_ATTACK"},
    ]
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", type=str, default="")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    pol = load_policy()
    if args.demo:
        j = demo_journal()
    elif args.journal:
        j = pd.read_csv(args.journal)
    else:
        print("Pass --journal CSV or --demo", file=sys.stderr)
        return 1
    out = summarize(j, pol)
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"trades={out['n_trades']}  WR={out['win_rate']:.1%}  next_size×={out['next_feedback_mult']:.2f}")
        print(f"approx path $1k → ${out['path_end_approx']:,.0f}  maxDD≈{out['path_max_dd_approx']:.1%}")
        for v, m in out["by_vehicle"].items():
            print(f"  {v}: n={m['n']} WR={m['wr']:.0%} avg={m['avg_pnl_pct']:+.1%}")
        print("Record real closes; do not retune SIDE rules from this file alone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
