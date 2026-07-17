#!/usr/bin/env python3
"""Robustness/stress evaluation for v86_anti_overfit_soft.

This is deliberately NOT a parameter hunt. The overlay rules in
``models/poc_va_macdha/v86_anti_overfit_soft/signal_engine.py`` are
pre-registered and explicitly "no retuning" -- re-tuning them against the
already-consumed 2024-08-01→2026-07-11 window would be exactly the in-sample
optimization AGENTS.md warns against elsewhere (see v72 self-healing round 2,
v85_online_contextual). Instead this script re-runs the frozen candidate,
unmodified, across additional evidence:

  1. The 4 rolling VALIDATION_FOLDS_1H OOS windows from tools/evolve/folds.py
     (F1-F4), to see whether the full/later headline numbers
     (results.json: +327% / -12.9% DD / Sharpe 2.88 / 76% WR) hold up
     sub-period by sub-period rather than being carried by one stretch.
  2. Cost/slippage stress (2x commission, 2x commission + spread haircut),
     reusing the StressedGlobalEquityEngine from tools/stress_backtest.py.

The untouched LOCKBOX window (2026-04-16→2026-07-11) is deliberately not
used here -- it was already consumed by prior v72 challenger work.

v72_dual_sleeve (the base v86 wraps) and v85_anti_overfit (a sibling
candidate) are run on the same windows for context, not as a promotion gate.

Usage:
  .venv/bin/python tools/evaluate_v86_anti_overfit_soft.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import dynamic_model_rank as dmr  # noqa: E402
from evolve.folds import VALIDATION_FOLDS_1H  # noqa: E402
from stress_backtest import install_stress_engine  # noqa: E402

OUTPUT = ROOT / "runs" / "v86_anti_overfit_soft"

CODES = ["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "XLP.US", "QQQ.US"]
CASH = 1000.0

WINDOWS: dict[str, tuple[str, str]] = {
    "full": ("2024-08-01", "2026-07-11"),
    "later": ("2025-08-01", "2026-07-11"),
    **{f["name"]: (f["oos_start"], f["oos_end"]) for f in VALIDATION_FOLDS_1H},
}
FOLD_NAMES = [f["name"] for f in VALIDATION_FOLDS_1H]

MODELS = ["v86_anti_overfit_soft", "v72_dual_sleeve", "v85_anti_overfit"]

STRESS_SCENARIOS = [
    {"id": "commission_2x", "stress_commission_per_side": 0.002, "slippage_bps": {}},
    {
        "id": "commission_2x_plus_spread",
        "stress_commission_per_side": 0.002,
        "slippage_bps": {
            "SPY.US": 5, "QQQ.US": 5, "XLP.US": 5,
            "TSLA.US": 10, "MU.US": 10, "IONQ.US": 20, "APLD.US": 20,
            "default": 10,
        },
    },
]


def run_matrix() -> list[dict[str, Any]]:
    discovered = {m["id"]: m for m in dmr.discover_models(MODELS)}
    rows: list[dict[str, Any]] = []
    for model_id in MODELS:
        model = discovered.get(model_id)
        if model is None:
            rows.append({"model": model_id, "window": None, "error": "model_not_discovered"})
            continue
        for window_name, (start, end) in WINDOWS.items():
            try:
                metrics = dmr.run_one(
                    model, mode="daily", codes=CODES, start=start, end=end,
                    tag=f"v86_eval_{window_name}", cash=CASH, source="local", interval="1H",
                )
                rows.append({
                    "model": model_id, "window": window_name, "start": start, "end": end,
                    "ret": metrics["ret"], "dd": metrics["dd"], "sharpe": metrics["sharpe"],
                    "n": metrics["n"], "wr": metrics["wr"], "final": metrics["final"], "error": None,
                })
            except RuntimeError as exc:
                rows.append({"model": model_id, "window": window_name, "start": start, "end": end, "error": str(exc)})
    return rows


def run_stress() -> list[dict[str, Any]]:
    install_stress_engine()
    model = dmr.discover_models(["v86_anti_overfit_soft"])[0]
    rows: list[dict[str, Any]] = []
    for scenario in STRESS_SCENARIOS:
        for window_name in ("full", "later"):
            start, end = WINDOWS[window_name]
            extra_cfg = {
                "stress_commission_per_side": scenario["stress_commission_per_side"],
                "slippage_bps": scenario["slippage_bps"],
            }
            try:
                metrics = dmr.run_one(
                    model, mode="daily", codes=CODES, start=start, end=end,
                    tag=f"v86_stress_{scenario['id']}_{window_name}", cash=CASH,
                    source="local", interval="1H", extra_cfg=extra_cfg,
                )
                rows.append({
                    "scenario": scenario["id"], "window": window_name, "start": start, "end": end,
                    "ret": metrics["ret"], "dd": metrics["dd"], "sharpe": metrics["sharpe"],
                    "n": metrics["n"], "wr": metrics["wr"], "final": metrics["final"], "error": None,
                })
            except RuntimeError as exc:
                rows.append({"scenario": scenario["id"], "window": window_name, "start": start, "end": end, "error": str(exc)})
    return rows


def _fmt_matrix_row(row: dict[str, Any]) -> str:
    if row.get("error"):
        return f"| {row['model']} | {row['window']} | ERROR: {row['error']} | | | | | |"
    return (
        f"| {row['model']} | {row['window']} | {row['start']}→{row['end']} | "
        f"{row['ret']:+.1%} | {row['dd']:.1%} | {row['sharpe']:.2f} | {row['n']} | "
        f"{row['wr']:.1%} | ${row['final']:,.0f} |"
    )


def _fmt_stress_row(row: dict[str, Any]) -> str:
    if row.get("error"):
        return f"| {row['scenario']} | {row['window']} | ERROR: {row['error']} | | | | |"
    return (
        f"| {row['scenario']} | {row['window']} | {row['ret']:+.1%} | {row['dd']:.1%} | "
        f"{row['sharpe']:.2f} | {row['n']} | {row['wr']:.1%} |"
    )


def build_gates(matrix: list[dict[str, Any]], stress: list[dict[str, Any]]) -> dict[str, Any]:
    by_key = {(r["model"], r["window"]): r for r in matrix if not r.get("error")}
    v86_folds = [by_key.get(("v86_anti_overfit_soft", f)) for f in FOLD_NAMES]
    v72_folds = [by_key.get(("v72_dual_sleeve", f)) for f in FOLD_NAMES]

    fold_consistency = {
        f: {
            "v86_ret": v86["ret"] if v86 else None,
            "v72_ret": v72["ret"] if v72 else None,
            "v86_beats_v72": (v86["ret"] >= v72["ret"]) if (v86 and v72) else None,
        }
        for f, v86, v72 in zip(FOLD_NAMES, v86_folds, v72_folds)
    }
    folds_no_deep_loss = all(
        (v["ret"] > -0.15) for v in v86_folds if v is not None
    ) if any(v86_folds) else False
    folds_majority_positive = (
        sum(1 for v in v86_folds if v is not None and v["ret"] > 0) >= 3
    ) if any(v86_folds) else False

    stress_by_key = {(r["scenario"], r["window"]): r for r in stress if not r.get("error")}
    stress_holds = all(
        r["ret"] > 0.0 for r in stress_by_key.values()
    ) if stress_by_key else False

    return {
        "fold_consistency": fold_consistency,
        "folds_no_single_fold_worse_than_neg15pct": folds_no_deep_loss,
        "folds_majority_positive_return": folds_majority_positive,
        "stress_all_scenarios_positive_return": stress_holds,
        "note": "informational robustness checks, not a promotion decision -- v86 remains research-only",
    }


def main() -> int:
    matrix = run_matrix()
    stress = run_stress()
    gates = build_gates(matrix, stress)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    state = {
        "schema_version": "v86-robustness-eval-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": "v86_anti_overfit_soft",
        "method": "frozen candidate re-run across rolling folds + cost/slippage stress; no parameter retuning",
        "matrix": matrix,
        "stress": stress,
        "gates": gates,
    }
    (OUTPUT / "STATE.json").write_text(json.dumps(state, indent=2, default=str) + "\n", encoding="utf-8")
    (OUTPUT / "COMPARE.json").write_text(json.dumps(matrix, indent=2, default=str) + "\n", encoding="utf-8")
    (OUTPUT / "STRESS.json").write_text(json.dumps(stress, indent=2, default=str) + "\n", encoding="utf-8")

    lines = [
        "# v86_anti_overfit_soft — rolling-fold + stress robustness check",
        "",
        "No parameter retuning. Overlay rules are frozen (see signal_engine.py docstring).",
        "",
        "## Windows",
        "",
        "| Model | Window | Range | Return | Max DD | Sharpe | Trades | WR | Final |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
        *[_fmt_matrix_row(r) for r in matrix],
        "",
        "## Cost / slippage stress (v86_anti_overfit_soft only)",
        "",
        "| Scenario | Window | Return | Max DD | Sharpe | Trades | WR |",
        "|---|---|---:|---:|---:|---:|---:|",
        *[_fmt_stress_row(r) for r in stress],
        "",
        "## Robustness gates (informational, not a promotion decision)",
        "",
        f"- Folds majority positive return: {gates['folds_majority_positive_return']}",
        f"- No single fold worse than -15%: {gates['folds_no_single_fold_worse_than_neg15pct']}",
        f"- All stress scenarios hold positive return: {gates['stress_all_scenarios_positive_return']}",
    ]
    (OUTPUT / "LEADERBOARD.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUTPUT / "LEADERBOARD.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
