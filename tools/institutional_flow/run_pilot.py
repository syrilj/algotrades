"""Pilot backtest for the reusable `tools/institutional_flow` feature module.

Runs a small 1H local-data backtest on three liquid US equities and compares
a heuristic model built on `tools.institutional_flow.compute_features` against
two baselines:
  - v60_microstructure (the prior microstructure research model, XGB/heuristic)
  - v39d_confluence (the current best single equity model)

The script also toggles the Almgren-Chriss impact overlay so we can measure the
cost of size-dependent execution on a $1,000 account.

Usage:
    .venv/bin/python tools/institutional_flow/run_pilot.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# tools/ is not in sys.path when this script is run directly, but dmr expects it.
TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import dynamic_model_rank as dmr

CODES = ["TSLA.US", "SPY.US", "QQQ.US"]
START = "2025-08-01"
END = "2026-07-11"
CASH = 1000
SOURCE = "local"
INTERVAL = "1H"
TAG = "pilot"


def _run(model_id: str, extra_cfg: dict | None = None) -> dict:
    models = dmr.discover_models([model_id])
    if not models:
        raise ValueError(f"model {model_id} not found")
    return dmr.run_one(
        models[0],
        mode="daily",
        codes=CODES,
        start=START,
        end=END,
        tag=TAG,
        cash=CASH,
        source=SOURCE,
        interval=INTERVAL,
        force_1d=False,
        reuse=False,
        extra_cfg=extra_cfg,
    )


def _fmt(row: dict) -> str:
    if row.get("error"):
        return f"{row['id']:28} ERROR {row['error']}"
    return (
        f"{row['id']:28} ret={row['ret']*100:6.1f}%  dd={row['dd']*100:5.1f}%  "
        f"sharpe={row['sharpe']:5.2f}  wr={row['wr']*100:4.0f}%  n={row['n']:3d}  "
        f"final=${row['final']:,.0f}"
    )


def main() -> int:
    print(f"Pilot: {CODES} | {START} -> {END} | cash=${CASH:,} | {INTERVAL}")

    # Baseline models
    v60 = _run("v60_microstructure")
    v39d = _run("v39d_confluence")

    # New reusable-feature model, standard slippage
    v61 = _run("v61_institutional_flow")

    # Same model with Almgren-Chriss impact overlay
    v61_ac = _run(
        "v61_institutional_flow",
        extra_cfg={
            "impact_model": "almgren_chriss",
            "ac_eta": 0.1,
            "ac_gamma": 0.0,
            "ac_beta": 0.5,
            "ac_adv_days": 20,
            "ac_vol_days": 20,
        },
    )

    rows = [v60, v39d, v61, v61_ac]
    print("\n=== PILOT RESULTS ===")
    for r in rows:
        print(_fmt(r))

    # Write a short report
    out_dir = Path(__file__).resolve().parent / "pilot_report"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / f"{TAG}_{START}_{END}.md", "w", encoding="utf-8") as f:
        f.write(f"# Institutional-flow pilot report\n\n")
        f.write(f"- Period: {START} -> {END}\n")
        f.write(f"- Symbols: {', '.join(CODES)}\n")
        f.write(f"- Cash: ${CASH:,}\n")
        f.write(f"- Interval: {INTERVAL}\n\n")
        f.write("| model | ret % | max DD % | Sharpe | win % | trades | final |\n")
        f.write("|-------|------:|----------:|--------:|------:|-------:|------:|\n")
        for r in rows:
            if r.get("error"):
                f.write(f"| {r['id']} | ERROR | - | - | - | - | - |\n")
            else:
                f.write(
                    f"| {r['id']} | {r['ret']*100:+.1f} | {r['dd']*100:.1f} | "
                    f"{r['sharpe']:.2f} | {r['wr']*100:.0f} | {r['n']} | ${r['final']:,.0f} |\n"
                )

    return 0


if __name__ == "__main__":
    sys.exit(main())
