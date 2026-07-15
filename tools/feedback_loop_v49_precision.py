#!/usr/bin/env python3
"""Record the single pre-registered high-precision v49 research iteration.

This command deliberately does not optimise, refit, or re-run a candidate.  It
only collects immutable run cards from the first causal evaluation and records
the feedback decision: retain a change only when it improves the constrained
objective, not merely the win rate.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "poc_va_dynamic_rank" / "runs"
OUT = ROOT / "runs" / "feedback_loop_v49_precision"
FOLDS = ("f1", "f2", "f3", "f4")


def _card(model: str, tag: str) -> dict:
    path = RUNS / model / f"{tag}__daily__c1000" / "run_card.json"
    card = json.loads(path.read_text())
    metrics = card["metrics"]
    return {
        "model": model,
        "tag": tag,
        "status": "completed",
        "start": card["backtest"]["start_date"],
        "end": card["backtest"]["end_date"],
        "ret": float(metrics["total_return"]),
        "dd": float(metrics["max_drawdown"]),
        "sharpe": float(metrics["sharpe"]),
        "pf": float(metrics["profit_factor"]),
        "n": int(metrics["trade_count"]),
        "wr": float(metrics["win_rate"]),
        "run_card": str(path.relative_to(ROOT)),
    }


def _table(rows: list[dict]) -> str:
    lines = [
        "# v49 precision-gate feedback report",
        "",
        "This is one pre-registered causal change, not an optimisation sweep.",
        "",
        "| scope | model | return | drawdown | Sharpe | PF | win rate | fills | status |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        scope = row["tag"].replace("v49_precision_", "")
        if row["status"] != "completed":
            lines.append(f"| {scope} | {row['model']} | — | — | — | — | — | — | {row['status']} |")
            continue
        lines.append(
            f"| {scope} | {row['model']} | {row['ret'] * 100:.2f}% | {row['dd'] * 100:.2f}% | "
            f"{row['sharpe']:.2f} | {row['pf']:.2f} | {row['wr'] * 100:.2f}% | {row['n']} | completed |"
        )
    return "\n".join(lines) + "\n"


def collect() -> dict:
    rows = [
        _card("v39d_causal", "v49_precision_control"),
        {
            "model": "v49_precision_trend",
            "tag": "v49_precision_compile",
            "status": "failed_technical",
            "error": "Runner AST rejected @staticmethod; removed before first valid evaluation.",
        },
        _card("v49_precision_trend", "v49_preregistered_full_r1"),
    ]
    for fold in FOLDS:
        rows.extend((
            _card("v39d_causal", f"v49_precision_{fold}"),
            _card("v49_precision_trend", f"v49_precision_{fold}"),
        ))
    controls = {row["tag"]: row for row in rows if row.get("model") == "v39d_causal"}
    challengers = [row for row in rows if row.get("model") == "v49_precision_trend" and row.get("status") == "completed"]
    fold_rows = [row for row in challengers if row["tag"] in {f"v49_precision_{fold}" for fold in FOLDS}]
    improvements = [
        row for row in fold_rows
        if row["ret"] > controls[row["tag"]]["ret"]
    ]
    win_improvements = [
        row for row in fold_rows
        if row["wr"] > controls[row["tag"]]["wr"]
    ]
    full = next(row for row in challengers if row["tag"] == "v49_preregistered_full_r1")
    decision = {
        "accepted": False,
        "reason": "Rejected: the full-window constrained objective worsened and drawdown exceeded 25%.",
        "full_window": {
            "return": full["ret"], "drawdown": full["dd"], "sharpe": full["sharpe"],
            "profit_factor": full["pf"], "win_rate": full["wr"],
        },
        "fold_return_improvements": len(improvements),
        "fold_win_rate_improvements": len(win_improvements),
        "feedback_rule": "Do not alter the score threshold after observing these outcomes.",
    }
    state = {
        "candidate": "v49_precision_trend",
        "trial_budget": 12,
        "trials_used": len(rows),
        "frozen": False,
        "promotion_status": "rejected_historical",
        "decision": decision,
        "trials": rows,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "STATE.json").write_text(json.dumps(state, indent=2, sort_keys=True))
    pd.DataFrame(rows).to_parquet(OUT / "trial_ledger.parquet", index=False)
    (OUT / "LEADERBOARD.md").write_text(_table(rows) + "\n## Feedback decision\n\n" + decision["reason"] + "\n")
    return state


if __name__ == "__main__":
    print(json.dumps(collect()["decision"], indent=2))
