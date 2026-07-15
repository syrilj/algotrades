#!/usr/bin/env python3
"""Parallel high-win-rate screen across the v39+ model zoo.

Usage:
    .venv/bin/python tools/search_high_win_rate.py --workers 2 --source local
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs" / "high_win_rate_search"

sys.path.insert(0, str(ROOT / "tools"))

import dynamic_model_rank as dmr  # noqa: E402
from evolve.farm import (  # noqa: E402
    EQUITY_WINNER_BAG,
    WINDOWS,
    discover,
    filter_track,
    run_batch,
)

DEFAULT_MODELS = [
    "v39b_live_adapt",
    "v39b_live_adapt_tight_stop_all",
    "v39d_confluence",
    "v39d_confluence_tight_stop_all",
    "v39d_causal",
    "v40_arete_pro",
    "v41_ensemble_feedback",
    "v42_trend_breakout",
    "v43_order_blocks",
    "v44_absorption",
    "v44_true_levels",
    "v45_ultimate_rsi",
    "v45b_ultimate_rsi_stops",
    "v46_lux_pivot_ghosts",
    "v47_causal",
    "v47_high_freq_edge",
    "v48_regime_barbell",
    "v49_precision_trend",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fmt(row: dict[str, Any]) -> str:
    if row.get("error"):
        return f"{row['id']:32} FAIL {row['error'][:80]}"
    return (
        f"{row['id']:32} wr={row.get('wr', 0) * 100:5.1f}% "
        f"ret={row.get('ret', 0) * 100:7.1f}% "
        f"dd={abs(row.get('dd', 0)) * 100:6.1f}% "
        f"sharpe={row.get('sharpe', 0):5.2f} "
        f"n={int(row.get('n', 0)):3d} "
        f"final=${row.get('final_at_cash') or row.get('final') or 0:>10,.2f}"
    )


def _leaderboard(rows: list[dict[str, Any]], target: float) -> str:
    ok = [r for r in rows if not r.get("error") and int(r.get("n", 0)) >= 5]
    ok.sort(key=lambda r: float(r.get("wr", 0)), reverse=True)

    lines = [
        f"# High win-rate search ({_now()})",
        "",
        f"- Universe: `{', '.join(EQUITY_WINNER_BAG)}`",
        f"- Window: `{WINDOWS['full'][0]}` to `{WINDOWS['full'][1]}`",
        f"- Target win rate: `{target * 100:.0f}%`",
        "",
        "| rank | model | wr | ret | dd | sharpe | n | final |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for i, r in enumerate(ok, 1):
        lines.append(
            f"| {i} | `{r['id']}` | {r.get('wr', 0) * 100:.1f}% | "
            f"{r.get('ret', 0) * 100:.1f}% | {abs(r.get('dd', 0)) * 100:.1f}% | "
            f"{r.get('sharpe', 0):.2f} | {int(r.get('n', 0))} | "
            f"${r.get('final_at_cash') or r.get('final') or 0:,.0f} |"
        )

    above = [r for r in ok if float(r.get("wr", 0)) >= target]
    lines += ["", f"Models hitting target: {len(above)}"]
    if above:
        lines += [""]
        for r in above:
            lines.append(f"- `{r['id']}`: wr={r.get('wr', 0) * 100:.1f}%, ret={r.get('ret', 0) * 100:.1f}%, n={int(r.get('n', 0))}")
    else:
        lines += ["", "No model hit the target. The best candidate will be gated/ensembled next."]

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="High win-rate model screen")
    parser.add_argument("--workers", type=int, default=2, help="Parallel backtest workers")
    parser.add_argument("--cash", type=float, default=1000.0)
    parser.add_argument("--source", type=str, default="local", help="Data source (local / yfinance)")
    parser.add_argument("--tag", type=str, default="high_wr_v1", help="Run tag")
    parser.add_argument("--target", type=float, default=0.80, help="Target win rate (0-1)")
    parser.add_argument("--models", type=str, default="", help="Comma-separated model ids (default: v39+ zoo)")
    args = parser.parse_args()

    only = [m.strip() for m in args.models.split(",") if m.strip()] or None
    if only:
        models = discover(only=only)
    else:
        models = discover(only=DEFAULT_MODELS)
    models = filter_track(models, "equity")
    if not models:
        print("No equity-runnable models found")
        return 1

    print(f"Running {len(models)} equity models on {EQUITY_WINNER_BAG} (workers={args.workers})")
    start, end = WINDOWS["full"]

    rows = run_batch(
        models,
        codes=EQUITY_WINNER_BAG,
        start=start,
        end=end,
        tag=args.tag,
        cash=args.cash,
        source=args.source,
        track="equity",
        workers=args.workers,
        reuse=False,
    )

    for r in sorted(rows, key=lambda x: float(x.get("wr", 0)), reverse=True):
        print(_fmt(r))

    # Strip non-serialisable artifacts
    clean_rows = []
    for r in rows:
        cr = {k: v for k, v in r.items() if isinstance(v, (str, int, float, bool, list, dict, type(None)))}
        clean_rows.append(cr)

    state = {
        "updated_at": _now(),
        "target_wr": args.target,
        "cash": args.cash,
        "source": args.source,
        "tag": args.tag,
        "codes": EQUITY_WINNER_BAG,
        "start": start,
        "end": end,
        "rows": clean_rows,
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "STATE.json").write_text(json.dumps(state, indent=2, default=str))
    (OUT / "LEADERBOARD.md").write_text(_leaderboard(rows, args.target))
    print(f"\nLeaderboard → {OUT / 'LEADERBOARD.md'}")
    print(f"State       → {OUT / 'STATE.json'}")

    ok = [r for r in rows if not r.get("error") and int(r.get("n", 0)) >= 5]
    if ok:
        best = max(ok, key=lambda r: float(r.get("wr", 0)))
        print(f"\nTop by win rate: {best['id']}  wr={best.get('wr', 0) * 100:.1f}%  ret={best.get('ret', 0) * 100:.1f}%  n={int(best.get('n', 0))}")
        if float(best.get("wr", 0)) >= args.target:
            print("Target hit.")
        else:
            print("Target not hit. Build a confidence gate / ensemble on top candidate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
