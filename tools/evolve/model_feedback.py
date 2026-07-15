"""Robust model ranking and persistent failure-guided evolution memory.

The ranking layer deliberately separates three concerns:

* performance: mean utility across comparable evaluation runs;
* robustness: dispersion, OOS reversals, and multi-lock failures;
* confidence: sample size and evaluation coverage.

Failures are stored as structured tags instead of free-form prose so later
generations can prefer mutations that address problems seen in prior runs.
"""
from __future__ import annotations

import copy
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from evolve.scoring import utility_score


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MEMORY_PATH = ROOT / "runs" / "evolve_memory" / "MODEL_MEMORY.json"
SCHEMA_VERSION = 1


FAILURE_ACTIONS: dict[str, str] = {
    "runtime_error": "Fix the engine/runtime error before spending more backtest budget.",
    "no_trades": "Relax entry gates or expand eligible symbols, then recheck signal generation.",
    "thin_sample": "Increase opportunity coverage or ease filters; do not promote on this sample.",
    "negative_return": "Change signal selectivity or portfolio composition; more size will not repair negative edge.",
    "weak_sharpe": "Improve entry quality or regime filtering before increasing risk.",
    "hard_drawdown": "Reduce position risk, tighten loss controls, or diversify concentrated exposure.",
    "oos_degradation": "Reduce complexity and retune on training data only; keep OOS frozen.",
    "unstable_windows": "Prefer changes that work across regimes instead of maximizing one window.",
    "multi_lock_failure": "Reject promotion and address the named holdout failure.",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except (TypeError, ValueError):
        return default


def _run_utility(row: dict[str, Any]) -> float:
    value = row.get("utility")
    return _num(value, utility_score(row)) if value is not None else utility_score(row)


def _is_oos(row: dict[str, Any]) -> bool:
    tag = str(row.get("tag") or "").lower()
    return any(token in tag for token in ("oos", "hold", "lock"))


def _failure(
    tag: str,
    severity: str,
    evidence: str,
    *,
    run_tag: str | None = None,
) -> dict[str, Any]:
    return {
        "tag": tag,
        "severity": severity,
        "evidence": evidence,
        "run_tag": run_tag,
        "action": FAILURE_ACTIONS[tag],
    }


def diagnose_model(
    model_id: str,
    runs: Iterable[dict[str, Any]],
    *,
    multi_lock: dict[str, Any] | None = None,
    min_trades: int = 40,
    hard_drawdown: float = 0.25,
    min_sharpe: float = 0.5,
) -> dict[str, Any]:
    """Return structured, de-duplicated reasons a model is not trustworthy."""
    rows = list(runs)
    failures: list[dict[str, Any]] = []
    valid = [r for r in rows if not r.get("error") and int(r.get("n") or 0) > 0]

    for row in rows:
        tag = str(row.get("tag") or "unspecified")
        if row.get("error"):
            failures.append(_failure("runtime_error", "critical", str(row["error"])[:180], run_tag=tag))
            continue
        n = int(row.get("n") or 0)
        if n <= 0:
            failures.append(_failure("no_trades", "critical", "trade_count=0", run_tag=tag))
            continue
        ret = _num(row.get("ret"))
        dd = abs(_num(row.get("dd", row.get("max_drawdown"))))
        sharpe = _num(row.get("sharpe"))
        if ret <= 0:
            failures.append(_failure("negative_return", "failure", f"return={ret:.4f}", run_tag=tag))
        if sharpe < min_sharpe:
            failures.append(
                _failure("weak_sharpe", "failure", f"sharpe={sharpe:.3f} < {min_sharpe:.3f}", run_tag=tag)
            )
        if dd >= hard_drawdown:
            failures.append(
                _failure(
                    "hard_drawdown",
                    "critical",
                    f"drawdown={dd:.3f} >= {hard_drawdown:.3f}",
                    run_tag=tag,
                )
            )

    total_trades = sum(int(r.get("n") or 0) for r in valid)
    if valid and total_trades < min_trades:
        failures.append(
            _failure(
                "thin_sample",
                "warning",
                f"pooled_trade_count={total_trades} < {min_trades}",
            )
        )

    if len(valid) >= 2:
        utilities = np.asarray([_run_utility(r) for r in valid], dtype=float)
        spread = float(utilities.std(ddof=0))
        mean_abs = abs(float(utilities.mean()))
        if spread > max(0.75, 0.60 * mean_abs):
            failures.append(
                _failure(
                    "unstable_windows",
                    "failure",
                    f"utility_std={spread:.3f}, utility_mean={utilities.mean():.3f}",
                )
            )

        train = [r for r in valid if not _is_oos(r)]
        oos = [r for r in valid if _is_oos(r)]
        if train and oos:
            train_ret = float(np.mean([_num(r.get("ret")) for r in train]))
            oos_ret = float(np.mean([_num(r.get("ret")) for r in oos]))
            train_u = float(np.mean([_run_utility(r) for r in train]))
            oos_u = float(np.mean([_run_utility(r) for r in oos]))
            if (train_ret > 0 >= oos_ret) or oos_u < train_u - max(0.75, abs(train_u) * 0.50):
                failures.append(
                    _failure(
                        "oos_degradation",
                        "critical",
                        f"train_ret={train_ret:.3f}, oos_ret={oos_ret:.3f}, "
                        f"train_utility={train_u:.3f}, oos_utility={oos_u:.3f}",
                    )
                )

    if multi_lock and not bool(multi_lock.get("ok")):
        status = str(multi_lock.get("status") or "FAIL")
        flags = multi_lock.get("flags") or [multi_lock.get("reason") or "unspecified"]
        failures.append(
            _failure("multi_lock_failure", "critical", f"status={status}; flags={flags}")
        )

    severity_order = {"warning": 1, "failure": 2, "critical": 3}
    grouped: dict[str, dict[str, Any]] = {}
    for item in failures:
        tag = item["tag"]
        if tag not in grouped:
            grouped[tag] = {**item, "count": 1, "evidence_all": [item["evidence"]]}
            continue
        current = grouped[tag]
        current["count"] += 1
        current["evidence_all"].append(item["evidence"])
        if severity_order[item["severity"]] > severity_order[current["severity"]]:
            current["severity"] = item["severity"]

    ordered = sorted(
        grouped.values(),
        key=lambda x: (-severity_order[x["severity"]], -int(x["count"]), x["tag"]),
    )
    return {
        "model_id": model_id,
        "status": "PASS" if not ordered else "FAIL",
        "failures": ordered,
        "failure_tags": [item["tag"] for item in ordered],
        "actions": [item["action"] for item in ordered],
        "runs_seen": len(rows),
        "valid_runs": len(valid),
        "total_trades": total_trades,
    }


def rank_model_runs(
    runs_by_model: dict[str, list[dict[str, Any]]],
    *,
    multi_lock: dict[str, dict[str, Any]] | None = None,
    min_trades: int = 40,
    expected_runs: int | None = None,
) -> list[dict[str, Any]]:
    """Aggregate comparable runs and rank stable, sufficiently tested models first."""
    ranked: list[dict[str, Any]] = []
    locks = multi_lock or {}

    for model_id, all_runs in runs_by_model.items():
        rows = list(all_runs)
        valid = [r for r in rows if not r.get("error") and int(r.get("n") or 0) > 0]
        diagnosis = diagnose_model(model_id, rows, multi_lock=locks.get(model_id), min_trades=min_trades)
        if not valid:
            base = dict(rows[0]) if rows else {"id": model_id}
            base.update(
                {
                    "id": model_id,
                    "rank_score": -99.0,
                    "rank_confidence": 0.0,
                    "rank_components": {"reason": "no_valid_runs"},
                    "failure_profile": diagnosis,
                }
            )
            ranked.append(base)
            continue

        utilities = np.asarray([_run_utility(r) for r in valid], dtype=float)
        mean_u = float(utilities.mean())
        std_u = float(utilities.std(ddof=0))
        stability_penalty = 0.50 * std_u
        oos_rows = [r for r in valid if _is_oos(r)]
        oos_penalty = 0.0
        if oos_rows:
            oos_ret = float(np.mean([_num(r.get("ret")) for r in oos_rows]))
            if oos_ret <= 0:
                oos_penalty = 1.0 + min(2.0, abs(oos_ret))

        lock = locks.get(model_id) or {}
        lock_penalty = 0.0
        if lock and not lock.get("ok"):
            lock_penalty = 0.5 if lock.get("status") in ("SKIP", "THIN") else 2.0

        total_trades = sum(int(r.get("n") or 0) for r in valid)
        sample_confidence = min(1.0, total_trades / max(1, min_trades))
        target_runs = expected_runs or max(1, len(rows))
        coverage = min(1.0, len(valid) / max(1, target_runs))
        confidence = sample_confidence * coverage
        confidence_penalty = 0.50 * (1.0 - confidence)
        rank_score = mean_u - stability_penalty - oos_penalty - lock_penalty - confidence_penalty

        base = dict(valid[0])
        for metric in ("ret", "dd", "sharpe", "wr"):
            base[metric] = float(np.mean([_num(r.get(metric)) for r in valid]))
        base["n"] = total_trades
        base.update(
            {
                "id": model_id,
                "utility": mean_u,
                "rank_score": float(rank_score),
                "rank_confidence": float(confidence),
                "evaluation_runs": len(valid),
                "rank_components": {
                    "mean_utility": mean_u,
                    "utility_std": std_u,
                    "stability_penalty": stability_penalty,
                    "oos_penalty": oos_penalty,
                    "multi_lock_penalty": lock_penalty,
                    "confidence_penalty": confidence_penalty,
                },
                "failure_profile": diagnosis,
            }
        )
        ranked.append(base)

    ranked.sort(key=lambda row: (_num(row.get("rank_score"), -99.0), _num(row.get("rank_confidence"))), reverse=True)
    for index, row in enumerate(ranked, 1):
        row["rank"] = index
    return ranked


def empty_memory() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "updated_at": _now(),
        "models": {},
        "mutations": {},
        "generations": [],
    }


def load_memory(path: Path | None = None) -> dict[str, Any]:
    memory_path = path or DEFAULT_MEMORY_PATH
    if not memory_path.exists():
        return empty_memory()
    try:
        payload = json.loads(memory_path.read_text())
        if not isinstance(payload, dict):
            return empty_memory()
        payload.setdefault("schema_version", SCHEMA_VERSION)
        payload.setdefault("models", {})
        payload.setdefault("mutations", {})
        payload.setdefault("generations", [])
        return payload
    except (OSError, json.JSONDecodeError):
        return empty_memory()


def save_memory(memory: dict[str, Any], path: Path | None = None) -> Path:
    memory_path = path or DEFAULT_MEMORY_PATH
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(memory)
    payload["schema_version"] = SCHEMA_VERSION
    payload["updated_at"] = _now()
    temporary = memory_path.with_suffix(memory_path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, default=str))
    temporary.replace(memory_path)
    return memory_path


def _mutation_name(row: dict[str, Any]) -> str | None:
    if row.get("mutation_name"):
        return str(row["mutation_name"])
    mutations = row.get("mutations") or []
    if mutations and isinstance(mutations[0], dict) and mutations[0].get("name"):
        return str(mutations[0]["name"])
    return None


def update_memory(
    memory: dict[str, Any],
    rankings: list[dict[str, Any]],
    *,
    generation: int | str,
    parent_scores: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Update model failure counts and mutation win/delta statistics."""
    out = copy.deepcopy(memory)
    models = out.setdefault("models", {})
    mutation_stats = out.setdefault("mutations", {})
    parents = parent_scores or {}

    for row in rankings:
        model_id = str(row.get("id") or "unknown")
        profile = row.get("failure_profile") or diagnose_model(model_id, [row])
        rec = models.setdefault(model_id, {"attempts": 0, "failures": {}})
        rec["attempts"] = int(rec.get("attempts", 0)) + 1
        rec["last_seen"] = _now()
        rec["latest_rank_score"] = _num(row.get("rank_score"), -99.0)
        rec["latest_rank_confidence"] = _num(row.get("rank_confidence"))
        rec["last_failure_tags"] = list(profile.get("failure_tags") or [])
        rec["last_actions"] = list(profile.get("actions") or [])
        failures = rec.setdefault("failures", {})
        for item in profile.get("failures") or []:
            tag = str(item.get("tag"))
            failures[tag] = int(failures.get(tag, 0)) + int(item.get("count", 1))

        mutation_name = _mutation_name(row)
        parent = str(row.get("parent") or "")
        if not mutation_name or parent not in parents:
            continue
        score = _num(row.get("rank_score"), _num(row.get("utility"), -99.0))
        delta = score - _num(parents[parent], -99.0)
        stat = mutation_stats.setdefault(
            mutation_name,
            {"attempts": 0, "wins": 0, "mean_delta": 0.0, "last_delta": 0.0},
        )
        attempts = int(stat.get("attempts", 0)) + 1
        old_mean = _num(stat.get("mean_delta"))
        stat["attempts"] = attempts
        stat["wins"] = int(stat.get("wins", 0)) + (1 if delta > 0 else 0)
        stat["mean_delta"] = old_mean + (delta - old_mean) / attempts
        stat["last_delta"] = delta
        stat["last_seen"] = _now()

    history = out.setdefault("generations", [])
    history.append(
        {
            "generation": generation,
            "recorded_at": _now(),
            "models": len(rankings),
            "best_id": rankings[0].get("id") if rankings else None,
            "best_rank_score": _num(rankings[0].get("rank_score"), -99.0) if rankings else None,
        }
    )
    out["generations"] = history[-100:]
    return out


def record_generation(
    rankings: list[dict[str, Any]],
    *,
    generation: int | str,
    parent_scores: dict[str, float] | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    memory = update_memory(load_memory(path), rankings, generation=generation, parent_scores=parent_scores)
    save_memory(memory, path)
    return memory


def _infer_targets(spec: dict[str, Any]) -> set[str]:
    explicit = spec.get("targets") or []
    if explicit:
        return {str(tag) for tag in explicit}
    text = f"{spec.get('name', '')} {spec.get('hypothesis', '')}".lower()
    targets: set[str] = set()
    if any(token in text for token in ("risk", "stop", "drawdown", "halt", "drop")):
        targets.add("hard_drawdown")
    if any(token in text for token in ("allow", "unblock", "lower threshold", "more trades", "expand")):
        targets.update(("no_trades", "thin_sample"))
    if any(token in text for token in ("confidence", "vwap", "structure", "select", "regime")):
        targets.update(("negative_return", "weak_sharpe", "unstable_windows"))
    if any(token in text for token in ("stress", "commission", "slippage")):
        targets.add("oos_degradation")
    return targets


def prioritize_mutation_menu(
    menu: list[dict[str, Any]],
    diagnoses: Iterable[dict[str, Any]],
    memory: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Order mutations by current failure fit, learned delta, and exploration."""
    mem = memory or empty_memory()
    failure_weight: dict[str, float] = {}
    model_memory = mem.get("models") or {}
    for profile in diagnoses:
        for item in profile.get("failures") or []:
            tag = str(item.get("tag"))
            failure_weight[tag] = failure_weight.get(tag, 0.0) + float(item.get("count", 1))
        historic = model_memory.get(str(profile.get("model_id"))) or {}
        for tag, count in (historic.get("failures") or {}).items():
            failure_weight[str(tag)] = failure_weight.get(str(tag), 0.0) + 0.25 * int(count)

    mutation_stats = mem.get("mutations") or {}
    scored: list[dict[str, Any]] = []
    for index, original in enumerate(menu):
        spec = copy.deepcopy(original)
        name = str(spec.get("name") or f"mutation_{index}")
        targets = _infer_targets(spec)
        target_score = sum(failure_weight.get(tag, 0.0) for tag in targets)
        stat = mutation_stats.get(name) or {}
        attempts = int(stat.get("attempts", 0))
        learned_delta = max(-3.0, min(3.0, _num(stat.get("mean_delta"))))
        win_rate = int(stat.get("wins", 0)) / attempts if attempts else 0.0
        exploration = 0.20 / math.sqrt(attempts + 1.0)
        priority = 2.0 * target_score + learned_delta + 0.25 * win_rate + exploration
        if name == "base":
            priority = 10_000.0  # Always retain a same-generation control arm.
        spec["feedback_priority"] = float(priority)
        spec["feedback_targets"] = sorted(targets)
        spec["feedback_reason"] = {
            "matched_failures": {tag: failure_weight[tag] for tag in targets if tag in failure_weight},
            "historical_mean_delta": learned_delta,
            "historical_attempts": attempts,
            "exploration_bonus": exploration,
        }
        spec["_original_order"] = index
        scored.append(spec)

    scored.sort(key=lambda spec: (-_num(spec.get("feedback_priority")), int(spec["_original_order"])))
    for spec in scored:
        spec.pop("_original_order", None)
    return scored
