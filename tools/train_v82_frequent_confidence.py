#!/usr/bin/env python3
"""Reconcile the fixed v82 two-tier frequent-confidence research model."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any, Dict

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import dynamic_model_rank as dmr  # noqa: E402

MODEL_ID = "v82_frequent_confidence"
CODES = [
    "APLD.US", "ARM.US", "COIN.US", "IONQ.US", "MSTR.US", "MU.US",
    "NVDA.US", "PLTR.US", "QQQ.US", "RKLB.US", "SPY.US", "TSLA.US", "XLP.US",
]
CORE_CODES = {"SPY.US", "QQQ.US", "XLP.US", "MU.US", "NVDA.US", "TSLA.US"}
WINDOWS = {
    "train_reference": ("2024-08-01", "2025-08-01"),
    "historical_check": ("2025-08-01", "2026-07-11"),
    "full": ("2024-08-01", "2026-07-11"),
}


def wilson_interval(wins: int, n: int, z: float = 1.959963984540054) -> list[float]:
    if n <= 0:
        return [0.0, 1.0]
    p = wins / n
    den = 1.0 + z * z / n
    centre = (p + z * z / (2.0 * n)) / den
    half = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * n)) / n) / den
    return [max(0.0, centre - half), min(1.0, centre + half)]


def trade_details(run_path: str) -> Dict[str, Any]:
    path = ROOT / run_path / "artifacts" / "trades.csv"
    if not path.exists():
        return {"closed_trades": 0, "median_holding_days": None}
    trades = pd.read_csv(path)
    closed = trades[trades["side"].astype(str).str.lower().eq("sell")].copy()
    by_symbol: Dict[str, Any] = {}
    for code, frame in closed.groupby("code"):
        wins = int((frame["pnl"] > 0).sum())
        by_symbol[str(code)] = {
            "n": int(len(frame)),
            "wins": wins,
            "win_rate": wins / len(frame),
        }
    tier_breakdown: Dict[str, Any] = {}
    for tier_name, symbols in (
        ("liquid_core_balanced", CORE_CODES),
        ("strict_satellite", set(CODES) - CORE_CODES),
    ):
        frame = closed[closed["code"].isin(symbols)]
        wins = int((frame["pnl"] > 0).sum())
        tier_breakdown[tier_name] = {
            "n": int(len(frame)),
            "wins": wins,
            "win_rate": wins / len(frame) if len(frame) else None,
        }
    return {
        "closed_trades": int(len(closed)),
        "median_holding_days": (
            float(closed["holding_days"].median()) if len(closed) else None
        ),
        "p90_holding_days": (
            float(closed["holding_days"].quantile(0.90)) if len(closed) else None
        ),
        "by_symbol": by_symbol,
        "tier_breakdown": tier_breakdown,
    }


def run() -> Dict[str, Any]:
    model = dmr.discover_models([MODEL_ID])[0]
    windows: Dict[str, Any] = {}
    for label, (start, end) in WINDOWS.items():
        row = dmr.run_one(
            model,
            mode="daily",
            codes=CODES,
            start=start,
            end=end,
            tag=f"reconcile_{label}",
            force_1d=False,
            reuse=False,
            cash=1000,
            source="local",
            interval="1H",
        )
        n = int(row.get("n", 0))
        wins = int(round(float(row.get("wr", 0.0)) * n))
        windows[label] = {
            k: row.get(k) for k in ("ret", "dd", "sharpe", "n", "wr", "final", "path")
        }
        windows[label]["wins"] = wins
        windows[label]["win_rate_wilson_95"] = wilson_interval(wins, n)
        windows[label].update(trade_details(str(row.get("path", ""))))

    hist = windows["historical_check"]
    result = {
        "model": MODEL_ID,
        "status": "retrospective_research_not_promoted",
        "data": {"source": "local", "interval": "1H", "cash": 1000, "codes": CODES},
        "confidence_kind": "uncalibrated_ordinal_rank_not_probability",
        "windows": windows,
        "frequency": {
            "historical_closed_trades": hist["n"],
            "historical_trades_per_month_approx": float(hist["n"]) / 11.3,
        },
        "promotion": {
            "promoted": False,
            "reasons": [
                "routing was designed after historical review",
                "no untouched forward window remains in the local two-year archive",
                "ordinal confidence is not calibrated probability",
            ],
            "next_gate": "forward paper trade without retuning, then calibrate by tier",
        },
    }
    out = ROOT / "models" / "poc_va_macdha" / MODEL_ID / "results.json"
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return result


if __name__ == "__main__":
    run()
