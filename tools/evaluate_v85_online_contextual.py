#!/usr/bin/env python3
"""Validate and summarize the frozen v85 causal benchmark artifacts."""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from evolve.episode_metrics import long_episode_metrics


ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = ROOT / "runs" / "poc_va_dynamic_rank" / "runs"
OUTPUT = ROOT / "runs" / "v85_online_contextual"
MODEL_RESULTS = ROOT / "models" / "poc_va_macdha" / "v85_online_contextual" / "results.json"

RUNS = {
    "v39d_confluence": {
        "full": "integrity_full_v2__daily__c1000",
        "later": "integrity_later_v2__daily__c1000",
    },
    "v71_live_confidence": {
        "full": "integrity_full_v2__daily__c1000",
        "later": "integrity_later_v2__daily__c1000",
    },
    "v72_dual_sleeve": {
        "full": "integrity_full_v2__daily__c1000",
        "later": "integrity_later_v2__daily__c1000",
    },
    "v81_high_confidence_boost": {
        "full": "integrity_full_v2__daily__c1000",
        "later": "integrity_later_v2__daily__c1000",
    },
    "v85_online_contextual": {
        "full": "v85_integrity_full__daily__c1000",
        "later": "v85_integrity_later__daily__c1000",
    },
}

EXPECTED_WINDOWS = {
    "full": ("2024-08-01", "2026-07-11"),
    "later": ("2025-08-01", "2026-07-11"),
}
EXPECTED_EXTRA_CFG = {
    "causal_execution": True,
    "causal_commission_rate": 0.0005,
    "commission": 0.0005,
    "slippage_us": 0.0005,
    "rebalance_tolerance": 0.05,
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_bundle_verified(run_dir: Path, contract: dict[str, Any]) -> bool:
    records = contract.get("model_source_dependency_hashes")
    if not isinstance(records, list) or not records:
        return False
    code_root = (run_dir / "code").resolve()
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            return False
        target = record.get("target")
        expected = record.get("sha256")
        if not isinstance(target, str) or not target or target in seen:
            return False
        if not isinstance(expected, str) or len(expected) != 64:
            return False
        artifact = (code_root / target).resolve()
        if code_root not in artifact.parents or not artifact.is_file():
            return False
        if _sha256(artifact) != expected:
            return False
        seen.add(target)

    dependencies = code_root / "DEPENDENCIES.json"
    if not dependencies.is_file():
        return False
    manifest = json.loads(dependencies.read_text(encoding="utf-8"))
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(files, list) or not files:
        return False
    for dependency in files:
        if not isinstance(dependency, dict):
            return False
        target = dependency.get("target")
        pinned = dependency.get("sha256")
        if not isinstance(target, str) or not isinstance(pinned, str):
            return False
        if target not in seen:
            return False
        artifact = (code_root / target).resolve()
        if code_root not in artifact.parents or _sha256(artifact) != pinned:
            return False
    return True


def _load_run(model: str, window: str, directory: str) -> dict[str, Any]:
    run_dir = RUN_ROOT / model / directory
    metrics_path = run_dir / "artifacts" / "metrics.csv"
    contract_path = run_dir / "request_contract.json"
    with metrics_path.open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    expected_start, expected_end = EXPECTED_WINDOWS[window]
    checks = {
        "model": contract.get("model_id") == model,
        "window": (contract.get("start"), contract.get("end"))
        == (expected_start, expected_end),
        "source": contract.get("source") == "local",
        "interval": contract.get("interval") == "1H",
        "cash": float(contract.get("cash", 0.0)) == 1000.0,
        "execution": contract.get("extra_cfg") == EXPECTED_EXTRA_CFG,
    }
    if not all(checks.values()):
        raise RuntimeError(f"benchmark contract mismatch for {model}/{window}: {checks}")
    numeric = {key: float(value) for key, value in row.items() if value not in (None, "")}
    trades = pd.read_csv(run_dir / "artifacts" / "trades.csv")
    episodes = long_episode_metrics(
        trades,
        initial_cash=1000.0,
        final_value=numeric["final_value"],
    )
    if episodes["reconciles_final_value"] is not True:
        raise RuntimeError(f"episode P&L does not reconcile for {model}/{window}")
    return {
        "model": model,
        "window": window,
        "run_dir": str(run_dir.relative_to(ROOT)),
        "metrics": numeric,
        "episodes": episodes,
        "request_contract_valid": True,
        "dependency_hash_count": len(contract.get("model_source_dependency_hashes") or []),
        "self_contained_dependency_bundle": _run_bundle_verified(run_dir, contract),
    }


def _fmt(row: dict[str, Any]) -> str:
    metrics = row["metrics"]
    episodes = row["episodes"]
    interval = f"{episodes['wilson_95_low']:.1%}–{episodes['wilson_95_high']:.1%}"
    return (
        f"| {row['model']} | {row['window']} | {metrics['total_return']:+.2%} | "
        f"{metrics['max_drawdown']:.2%} | {metrics['sharpe']:.3f} | "
        f"{episodes['closed_episodes']} | {episodes['win_rate']:.2%} ({interval}) | "
        f"${metrics['final_value']:,.2f} |"
    )


def main() -> int:
    rows = [
        _load_run(model, window, directory)
        for model, windows in RUNS.items()
        for window, directory in windows.items()
    ]
    by_key = {(row["model"], row["window"]): row["metrics"] for row in rows}
    v85_full = by_key[("v85_online_contextual", "full")]
    v85_later = by_key[("v85_online_contextual", "later")]
    v72_full = by_key[("v72_dual_sleeve", "full")]
    v72_later = by_key[("v72_dual_sleeve", "later")]
    row_by_key = {(row["model"], row["window"]): row for row in rows}
    v85_full_episodes = row_by_key[("v85_online_contextual", "full")]["episodes"]
    v85_later_episodes = row_by_key[("v85_online_contextual", "later")]["episodes"]
    v72_full_episodes = row_by_key[("v72_dual_sleeve", "full")]["episodes"]
    v72_later_episodes = row_by_key[("v72_dual_sleeve", "later")]["episodes"]

    def _model_window(window: str) -> dict[str, Any]:
        row = row_by_key[("v85_online_contextual", window)]
        metrics = row["metrics"]
        episodes = row["episodes"]
        start, end = EXPECTED_WINDOWS[window]
        return {
            "start": start,
            "end": end,
            "return": metrics["total_return"],
            "max_drawdown": metrics["max_drawdown"],
            "sharpe": metrics["sharpe"],
            "final_value": metrics["final_value"],
            "execution_records": int(metrics["trade_count"]),
            "execution_record_win_rate": metrics["win_rate"],
            "closed_episodes": episodes["closed_episodes"],
            "episode_wins": episodes["wins"],
            "episode_win_rate": episodes["win_rate"],
            "episode_win_rate_wilson_95": [
                episodes["wilson_95_low"],
                episodes["wilson_95_high"],
            ],
        }

    gates = {
        "full_return_at_least_v72": v85_full["total_return"] >= v72_full["total_return"],
        "later_return_at_least_v72": v85_later["total_return"] >= v72_later["total_return"],
        "full_sharpe_margin_at_least_0_10": v85_full["sharpe"]
        >= v72_full["sharpe"] + 0.10,
        "later_sharpe_margin_at_least_0_10": v85_later["sharpe"]
        >= v72_later["sharpe"] + 0.10,
        "full_drawdown_no_worse_than_v72": v85_full["max_drawdown"]
        >= v72_full["max_drawdown"],
        "later_drawdown_no_worse_than_v72": v85_later["max_drawdown"]
        >= v72_later["max_drawdown"],
        "full_episode_win_rate_at_least_v72": v85_full_episodes["win_rate"]
        >= v72_full_episodes["win_rate"],
        "later_episode_win_rate_at_least_v72": v85_later_episodes["win_rate"]
        >= v72_later_episodes["win_rate"],
        "high_confidence_80pct_wilson_floor": v85_later_episodes["wilson_95_low"]
        >= 0.80,
        "frozen_dependency_bundle": all(
            row_by_key[("v85_online_contextual", window)][
                "self_contained_dependency_bundle"
            ]
            for window in EXPECTED_WINDOWS
        ),
        "untouched_holdout": False,
        "recorded_live_restart_parity_evidence": False,
        "live_runtime_endpoint_enabled": False,
        "forward_paper_complete": False,
        "probability_calibrated": False,
    }
    promoted = all(gates.values())
    state = {
        "schema_version": "v85-evaluation-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": "v85_online_contextual",
        "status": "research_only" if not promoted else "promotion_candidate",
        "promoted": promoted,
        "execution_contract": EXPECTED_EXTRA_CFG,
        "rows": rows,
        "promotion_gates": gates,
        "verdict": (
            "Not promoted. v85 materially reduces drawdown and improves later-period Sharpe, "
            "but it gives up return, has no untouched holdout, is not enabled on the live runtime, "
            "has no completed forward-paper window, and exposes no calibrated probability."
        ),
        "comparability_note": "reported win rates reconstruct closed episodes from all fills and commissions",
        "engineering_evidence": {
            "restart_replay_unit_test": "tests/market_runtime/test_adaptive_replay.py",
            "promotion_gate_requires_live_integration_evidence": True,
        },
    }

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "STATE.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    (OUTPUT / "COMPARE.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# v85 online contextual — causal integrity benchmark",
        "",
        "| Model | Window | Return | Max DD | Sharpe | Closed episodes | Episode WR (95% CI) | Final |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
        *[_fmt(row) for row in rows],
        "",
        "Episode metrics collapse partial resizes and include all recorded commissions.",
        "",
        "## Verdict",
        "",
        state["verdict"],
        "",
        "The full-window Sharpe edge over v72 is only 0.004 and is not treated as a "
        "statistically meaningful win. The later-period risk improvement is useful enough "
        "to justify forward paper trading, not live promotion.",
        "",
        "v85 episode precision is 73.5% full and 62.3% later; its Wilson intervals overlap "
        "v72 and do not support an 80–90% probability claim.",
    ]
    (OUTPUT / "LEADERBOARD.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    model_results = {
        "status": "research_only",
        "promoted": False,
        "source": "local",
        "interval": "1H",
        "cash": 1000.0,
        "execution": EXPECTED_EXTRA_CFG,
        "full": _model_window("full"),
        "later": _model_window("later"),
        "later_is_untouched_holdout": False,
        "confidence_kind": "ordinal_online_expert_support_not_probability",
        "verdict": (
            "Lower drawdown and stronger later-period Sharpe than v72, but lower return "
            "and no untouched holdout or completed forward-paper evidence."
        ),
    }
    MODEL_RESULTS.write_text(json.dumps(model_results, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT / "LEADERBOARD.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
