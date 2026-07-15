#!/usr/bin/env python3
"""A/B test: v39d baseline vs v68 VIX+oil risk-on gate.

Default: single-name IONQ (high beta) on the standard equity window.
Also runs the high-beta subset and full EQUITY_WINNER_BAG for context.

Usage:
  .venv/bin/python tools/test_v68_vix_oil.py
  .venv/bin/python tools/test_v68_vix_oil.py --codes IONQ.US --cash 1000
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import dynamic_model_rank as dmr  # noqa: E402
from tools.evolve.farm import EQUITY_WINNER_BAG  # noqa: E402

START = "2024-08-01"
END = "2026-07-11"


def _run(model_name: str, codes: list[str], tag: str, cash: float) -> dict:
    models = dmr.discover_models([model_name])
    if not models:
        raise SystemExit(f"model not found: {model_name}")
    m = models[0]
    return dmr.run_one(
        m,
        mode="daily",
        codes=codes,
        start=START,
        end=END,
        tag=tag,
        force_1d=False,
        cash=cash,
        source="local",
        interval="1H",
        reuse=False,
    )


def _fmt(r: dict) -> str:
    return (
        f"ret={r['ret']*100:6.1f}%  dd={r['dd']*100:6.1f}%  "
        f"sharpe={r['sharpe']:5.2f}  n={r['n']:3d}  wr={r['wr']*100:5.1f}%  "
        f"final=${r['final']:,.0f}"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", default="IONQ.US", help="comma-separated codes")
    ap.add_argument("--cash", type=float, default=1000.0)
    ap.add_argument("--also-bag", action="store_true", help="also run full winner bag")
    ap.add_argument(
        "--also-high-beta",
        action="store_true",
        help="also run IONQ+APLD+TSLA+MU",
    )
    args = ap.parse_args()

    suites = {
        "ionq": [c.strip() for c in args.codes.split(",") if c.strip()],
    }
    if args.also_high_beta:
        suites["high_beta"] = ["IONQ.US", "APLD.US", "TSLA.US", "MU.US"]
    if args.also_bag:
        suites["winner_bag"] = list(EQUITY_WINNER_BAG)

    report = {"start": START, "end": END, "cash": args.cash, "suites": {}}
    print(f"Window {START} → {END} | cash=${args.cash:,.0f} | source=local 1H")
    print("=" * 72)

    for suite_name, codes in suites.items():
        print(f"\n### suite={suite_name}  codes={codes}")
        base = _run("v39d_confluence", codes, f"v68ab_base_{suite_name}", args.cash)
        gated = _run("v68_vix_oil_riskon", codes, f"v68ab_gate_{suite_name}", args.cash)
        print(f"  v39d baseline : {_fmt(base)}")
        print(f"  v68 vix+oil   : {_fmt(gated)}")
        d_ret = (gated["ret"] - base["ret"]) * 100
        d_dd = (gated["dd"] - base["dd"]) * 100
        d_sh = gated["sharpe"] - base["sharpe"]
        print(f"  delta         : ret {d_ret:+.1f}pp  dd {d_dd:+.1f}pp  sharpe {d_sh:+.2f}")
        report["suites"][suite_name] = {
            "codes": codes,
            "baseline": {k: base[k] for k in ("ret", "dd", "sharpe", "n", "wr", "final")},
            "gated": {k: gated[k] for k in ("ret", "dd", "sharpe", "n", "wr", "final")},
            "delta_ret_pp": d_ret,
            "delta_dd_pp": d_dd,
            "delta_sharpe": d_sh,
        }

    out = ROOT / "runs" / "v68_vix_oil_riskon" / "AB_REPORT.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"\nWrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
