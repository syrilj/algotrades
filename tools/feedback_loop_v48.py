#!/usr/bin/env python3
"""Controlled v48 research, freeze, and prospective-shadow workflow."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import dynamic_model_rank as dmr  # noqa: E402
from evolve.v48_validation import (  # noqa: E402
    build_frozen_manifest,
    load_signal_engine,
    run_causal_invariance_suite,
    validate_data_contract,
)


OUT = ROOT / "runs" / "feedback_loop_v48"
STATE_PATH = OUT / "STATE.json"
LEADERBOARD_PATH = OUT / "LEADERBOARD.md"
FROZEN_PATH = OUT / "FROZEN_MANIFEST.json"
SHADOW_PATH = OUT / "SHADOW_REPORT.md"
TRIAL_PATH = OUT / "trial_ledger.parquet"
DEFAULT_CODES = ["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "XLP.US", "QQQ.US"]
POLICIES = ("static_80_20", "static_75_25", "static_67_33", "regime", "regime_feedback")
CONTROLS = ("v39d_causal", "v47_causal")
MAX_TRIALS = 12


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_state() -> dict[str, Any]:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"version": "v48", "trials": [], "frozen": False}


def _write_state(state: dict[str, Any]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _now()
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))


def _model(model_id: str) -> dict[str, Any]:
    models = {item["id"]: item for item in dmr.discover_models([model_id])}
    if model_id not in models:
        raise KeyError(f"model not found: {model_id}")
    return models[model_id]


def _cache_path(code: str, interval: str = "1h") -> Path:
    bare = code.replace(".US", "")
    return ROOT / "data_cache" / interval / f"{bare}.parquet"


def _load_data(codes: list[str]) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for code in codes:
        path = _cache_path(code)
        if not path.exists():
            raise FileNotFoundError(f"missing local 1H data for {code}: {path}")
        frames[code] = pd.read_parquet(path)
    return frames


def _audit(codes: list[str]) -> dict[str, Any]:
    frames = _load_data(codes)
    contract = validate_data_contract(frames, expected_symbols=codes)
    results: dict[str, Any] = {"data_contract": contract, "invariance": {}}
    for model_id in (*CONTROLS, "v48_regime_barbell"):
        engine = load_signal_engine(ROOT / "models" / "poc_va_macdha" / model_id)
        results["invariance"][model_id] = run_causal_invariance_suite(engine, frames)
    return results


def _run(model_id: str, policy: str | None, args: argparse.Namespace) -> dict[str, Any]:
    model = _model(model_id)
    extra: dict[str, Any] = {
        "causal_execution": True,
        "slippage_us": 0.0005,
        "causal_commission_rate": 0.0005,
    }
    tag = "v48_control"
    if policy is not None:
        extra["v48"] = {"policy": policy, "strict_regime": True}
        tag = f"v48_{policy}"
    row = dmr.run_one(
        model,
        mode="daily",
        codes=args.codes,
        start=args.start,
        end=args.end,
        tag=tag,
        force_1d=False,
        reuse=False,
        cash=args.cash,
        source="local",
        interval="1H",
        extra_cfg=extra,
    )
    row["policy"] = policy or model_id
    row["trial_type"] = "policy" if policy else "control"
    row["timestamp"] = _now()
    return row


def _eligible(row: dict[str, Any]) -> bool:
    return (
        not row.get("error")
        and float(row.get("ret", 0.0)) > 0.0
        and abs(float(row.get("dd", 0.0))) <= 0.25
        and float(row.get("sharpe", 0.0)) >= 0.80
        and int(row.get("n", 0)) >= 40
    )


def _leaderboard(trials: list[dict[str, Any]]) -> str:
    rows = sorted(trials, key=lambda row: float(row.get("ret", -999.0)), reverse=True)
    lines = ["# v48 research leaderboard", "", "Historical results are provisional; the future shadow is binding.", "", "| candidate | return | drawdown | Sharpe | trades | eligible |", "|---|---:|---:|---:|---:|---:|"]
    for row in rows:
        candidate = row.get("policy", row.get("id", "unknown"))
        lines.append(
            f"| {candidate} | {float(row.get('ret', 0))*100:.2f}% | {float(row.get('dd', 0))*100:.2f}% | {float(row.get('sharpe', 0)):.2f} | {int(row.get('n', 0))} | {_eligible(row)} |"
        )
    return "\n".join(lines) + "\n"


def command_audit(args: argparse.Namespace) -> int:
    state = _load_state()
    state["audit"] = _audit(args.codes)
    _write_state(state)
    print(json.dumps(state["audit"], indent=2))
    return 0


def command_research(args: argparse.Namespace) -> int:
    state = _load_state()
    if "audit" not in state:
        state["audit"] = _audit(args.codes)
    if len(state.get("trials", [])) >= MAX_TRIALS:
        raise RuntimeError(f"trial budget exhausted ({MAX_TRIALS})")
    scheduled: list[tuple[str, str | None]] = [(model, None) for model in CONTROLS]
    scheduled.extend(("v48_regime_barbell", policy) for policy in POLICIES)
    remaining = MAX_TRIALS - len(state.get("trials", []))
    rows = [_run(model, policy, args) for model, policy in scheduled[:remaining]]
    state.setdefault("trials", []).extend(rows)
    state["trial_budget"] = MAX_TRIALS
    candidates = [row for row in state["trials"] if row.get("id") == "v48_regime_barbell" and _eligible(row)]
    state["provisional_winner"] = max(candidates, key=lambda row: float(row["ret"])) if candidates else None
    _write_state(state)
    pd.DataFrame(state["trials"]).to_parquet(TRIAL_PATH, index=False)
    LEADERBOARD_PATH.write_text(_leaderboard(state["trials"]))
    print(LEADERBOARD_PATH)
    return 0


def command_freeze(args: argparse.Namespace) -> int:
    state = _load_state()
    winner = state.get("provisional_winner")
    if not winner:
        raise RuntimeError("no eligible v48 provisional winner; run research first")
    manifest = build_frozen_manifest(
        model_dir=ROOT / "models" / "poc_va_macdha" / "v48_regime_barbell",
        policy=str(winner["policy"]),
        data_contract=state["audit"]["data_contract"],
        trial_count=len(state.get("trials", [])),
    )
    manifest.update({"frozen_at": _now(), "research_metrics": winner, "shadow_requirement": {"min_calendar_months": 3, "min_completed_trades": 50}})
    OUT.mkdir(parents=True, exist_ok=True)
    FROZEN_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    state["frozen"] = True
    state["frozen_policy"] = winner["policy"]
    _write_state(state)
    print(FROZEN_PATH)
    return 0


def command_shadow(args: argparse.Namespace) -> int:
    if not FROZEN_PATH.exists():
        raise RuntimeError("no frozen manifest; run freeze first")
    frozen = json.loads(FROZEN_PATH.read_text())
    policy = str(frozen["policy"])
    baseline = _run("v39d_causal", None, args)
    candidate = _run("v48_regime_barbell", policy, args)
    elapsed_days = (pd.Timestamp(args.end) - pd.Timestamp(args.start)).days
    promotion_ready = (
        elapsed_days >= 90
        and int(candidate.get("n", 0)) >= 50
        and _eligible(candidate)
        and float(candidate.get("ret", 0.0)) > float(baseline.get("ret", 0.0))
    )
    report = {
        "frozen_policy": policy,
        "window": {"start": args.start, "end": args.end},
        "baseline": baseline,
        "candidate": candidate,
        "promotion_ready": promotion_ready,
        "note": "No tuning was performed during this shadow report.",
    }
    SHADOW_PATH.write_text("# v48 shadow report\n\n```json\n" + json.dumps(report, indent=2) + "\n```\n")
    print(SHADOW_PATH)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("audit-baselines", "research", "freeze", "shadow-report"))
    parser.add_argument("--start", default="2024-08-01")
    parser.add_argument("--end", default="2026-07-11")
    parser.add_argument("--cash", type=float, default=1000.0)
    parser.add_argument("--codes", default=",".join(DEFAULT_CODES))
    args = parser.parse_args()
    args.codes = [code.strip() for code in args.codes.split(",") if code.strip()]
    return {
        "audit-baselines": command_audit,
        "research": command_research,
        "freeze": command_freeze,
        "shadow-report": command_shadow,
    }[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
