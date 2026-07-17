"""Champion-relative, behavior-aware search for the v72 dual-sleeve model.

The legacy direction loop was designed around v39b's literal ``_ROUTING`` and
``_GENOME`` dictionaries. v72 has a different, cleaner contract: four sleeve
parameters in ``hunt_config.json`` are read directly by its live engine. This
module searches those effective parameters, evaluates every proposal on the
same rolling folds as a frozen v72 control, and rejects behavioral no-ops.
"""
from __future__ import annotations

import hashlib
import json
import random
import shutil
from pathlib import Path
from typing import Any

import pandas as pd

from tools.evolve import folds
from tools.evolve.loop_core import _build_model, _set_bridge, run_candidate
from tools.evolve.model_feedback import rank_model_runs

ROOT = Path(__file__).resolve().parents[2]
CHAMPION_DIR = ROOT / "models" / "poc_va_macdha" / "v72_dual_sleeve"
WINNER_BAG = [
    "TSLA.US",
    "MU.US",
    "SPY.US",
    "IONQ.US",
    "APLD.US",
    "XLP.US",
    "QQQ.US",
]

PARAM_BOUNDS: dict[str, tuple[float, float]] = {
    "core_scale": (0.55, 1.10),
    "both_core_frac": (0.05, 0.65),
    "max_weight": (0.30, 0.50),
    "sniper_min_conf": (0.00, 0.85),
}

BASE_STEPS: dict[str, float] = {
    "core_scale": 0.12,
    "both_core_frac": 0.14,
    "max_weight": 0.05,
    "sniper_min_conf": 0.16,
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(f".{path.name}.pending")
    pending.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    pending.replace(path)


def hunt_signature(hunt: dict[str, Any]) -> str:
    effective = {
        key: round(float(hunt.get(key, 0.0)), 6)
        for key in sorted(PARAM_BOUNDS)
    }
    return hashlib.sha256(
        json.dumps(effective, sort_keys=True).encode("utf-8")
    ).hexdigest()


def behavior_hash(candidate: dict[str, Any]) -> str:
    """Hash realized trades/equity so parameter-only no-ops are detectable."""
    digest = hashlib.sha256()
    trades = candidate.get("trades")
    equity = candidate.get("equity")
    if isinstance(trades, pd.DataFrame):
        cols = [
            column
            for column in (
                "entry_time",
                "exit_time",
                "symbol",
                "direction",
                "entry_price",
                "exit_price",
                "size",
                "pnl",
            )
            if column in trades.columns
        ]
        normalized = trades[cols].copy()
        for column in normalized.select_dtypes(include="number").columns:
            normalized[column] = normalized[column].astype(float).round(10)
        digest.update(pd.util.hash_pandas_object(normalized, index=True).values.tobytes())
    if isinstance(equity, pd.Series):
        normalized_equity = equity.astype(float).round(10)
        digest.update(
            pd.util.hash_pandas_object(normalized_equity, index=True).values.tobytes()
        )
    return digest.hexdigest()


def _clip(key: str, value: float) -> float:
    lower, upper = PARAM_BOUNDS[key]
    return round(min(upper, max(lower, float(value))), 4)


def sample_hunt(
    parent: dict[str, Any],
    rng: random.Random,
    *,
    exploration: float = 1.0,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Sparse Gaussian mutation over parameters the v72 engine consumes."""
    child = dict(parent)
    keys = list(PARAM_BOUNDS)
    touched = rng.sample(keys, rng.randint(1, min(3, len(keys))))
    changes: list[dict[str, Any]] = []
    for key in touched:
        current = float(child.get(key, 0.0))
        proposed = _clip(key, current + rng.gauss(0.0, BASE_STEPS[key] * exploration))
        # A clipped draw can land back on the parent. Force a bounded step.
        if proposed == round(current, 4):
            direction = -1.0 if current > sum(PARAM_BOUNDS[key]) / 2 else 1.0
            proposed = _clip(key, current + direction * BASE_STEPS[key] * exploration)
        child[key] = proposed
        changes.append({"parameter": key, "old": current, "new": proposed})
    child["selection_rule"] = "rolling_validation_search_lockbox_forbidden"
    child["research_only"] = True
    return child, changes


def materialize_variant(
    source_dir: Path,
    dest_dir: Path,
    hunt: dict[str, Any],
    *,
    parent_id: str,
    changes: list[dict[str, Any]],
) -> Path:
    """Copy a minimal v72 bundle and stamp an effective hunt configuration."""
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True)
    for name in ("signal_engine.py", "config.json", "hunt_config.json"):
        source = source_dir / name
        if not source.exists() and name != "hunt_config.json":
            raise FileNotFoundError(f"required v72 bundle file missing: {source}")
        if source.exists():
            shutil.copy2(source, dest_dir / name)
    _atomic_json(dest_dir / "hunt_config.json", hunt)
    config = _read_json(dest_dir / "config.json")
    strategy = config.get("strategy") if isinstance(config.get("strategy"), dict) else {}
    strategy.update(
        {
            "name": "v72_dual_sleeve_research",
            "model_version": dest_dir.name,
            "parent": parent_id,
            "promotion_eligible": False,
        }
    )
    config["strategy"] = strategy
    _atomic_json(dest_dir / "config.json", config)
    _atomic_json(
        dest_dir / "MUTATION.json",
        {
            "parent": parent_id,
            "changes": changes,
            "hunt_signature": hunt_signature(hunt),
            "research_only": True,
        },
    )
    return dest_dir


def _fold_runs(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            **metrics,
            "id": candidate["id"],
            "tag": fold_name,
        }
        for fold_name, metrics in (candidate.get("fold_metrics") or {}).items()
    ]


def _cycle_number(campaign_id: str) -> int:
    digits = "".join(character for character in campaign_id if character.isdigit())
    return int(digits[-4:] or 0)


def _rank_score(row: dict[str, Any]) -> float:
    """Return a sortable score without treating a legitimate zero as missing."""
    value = row.get("rank_score")
    return -999.0 if value is None else float(value)


def run_v72_campaign(
    base_model_dir: Path,
    *,
    generations: int = 1,
    cash: float = 1_000.0,
    campaign_id: str = "self_healing_v72",
    menu: list[dict[str, Any]] | None = None,
    memory_path: Path | None = None,
    qualify_generation_best: bool = False,
    max_variants_per_generation: int | None = 8,
) -> list[dict[str, Any]]:
    """Search v72 sleeve parameters relative to a frozen champion control.

    ``menu`` and ``qualify_generation_best`` are accepted for compatibility
    with the generic controller. This research runner never opens a lockbox.
    """
    del menu, qualify_generation_best
    if not CHAMPION_DIR.is_dir():
        raise FileNotFoundError(f"v72 champion bundle missing: {CHAMPION_DIR}")
    _set_bridge("1h")
    budget = max(1, int(max_variants_per_generation or 8))
    cycle = _cycle_number(campaign_id)
    report_root = (
        memory_path.parent if memory_path is not None else ROOT / "runs" / "self_healing_v72"
    ) / "v72_search"
    report_root.mkdir(parents=True, exist_ok=True)
    tried_path = report_root / "TRIALS.jsonl"
    behaviors_path = report_root / "BEHAVIORS.json"
    tried: set[str] = set()
    if tried_path.exists():
        for line in tried_path.read_text().splitlines():
            try:
                row = json.loads(line)
                if row.get("hunt_signature"):
                    tried.add(str(row["hunt_signature"]))
            except json.JSONDecodeError:
                continue
    prior_behaviors = _read_json(behaviors_path)
    known_behaviors = {
        str(key): str(value)
        for key, value in prior_behaviors.items()
        if key and value
    }

    parent_dir = Path(base_model_dir).resolve()
    all_results: list[dict[str, Any]] = []
    for generation in range(generations):
        generation_dir = report_root / campaign_id / f"gen_{generation:02d}"
        generation_dir.mkdir(parents=True, exist_ok=True)

        control_model = _build_model(CHAMPION_DIR)
        control = run_candidate(
            control_model,
            codes=WINNER_BAG,
            cash=cash,
            campaign_id=campaign_id,
            gen=generation,
            variant_id=f"v72_control_c{cycle:04d}_g{generation}",
            parent="v72_dual_sleeve",
            fold_set=folds.VALIDATION_FOLDS_1H,
        )
        control["is_control"] = True
        control["mutation_name"] = "champion_control"
        control["hunt"] = _read_json(CHAMPION_DIR / "hunt_config.json")
        control["hunt_signature"] = hunt_signature(control["hunt"])
        control["behavior_hash"] = behavior_hash(control)
        control["no_op"] = False

        parent_hunt = _read_json(parent_dir / "hunt_config.json")
        if not parent_hunt:
            parent_hunt = dict(control["hunt"])
            parent_dir = CHAMPION_DIR
        seed_payload = f"{campaign_id}:{generation}:{parent_dir}:{cash}"
        seed = int(hashlib.sha256(seed_payload.encode("utf-8")).hexdigest()[:16], 16)
        rng = random.Random(seed)
        exploration = min(2.25, 1.0 + 0.12 * max(0, cycle - 1))
        variants: list[dict[str, Any]] = []
        seen_hunts = {control["hunt_signature"], hunt_signature(parent_hunt), *tried}
        attempts = 0
        while len(variants) < budget and attempts < budget * 40:
            attempts += 1
            mutation_parent = parent_hunt if attempts % 3 else control["hunt"]
            hunt, changes = sample_hunt(mutation_parent, rng, exploration=exploration)
            signature = hunt_signature(hunt)
            if signature in seen_hunts:
                continue
            seen_hunts.add(signature)
            variant_id = f"v72c{cycle:04d}g{generation}_{len(variants):02d}_{signature[:8]}"
            variant_dir = materialize_variant(
                parent_dir if attempts % 3 else CHAMPION_DIR,
                generation_dir / variant_id,
                hunt,
                parent_id=parent_dir.name,
                changes=changes,
            )
            model = _build_model(variant_dir)
            candidate = run_candidate(
                model,
                codes=WINNER_BAG,
                cash=cash,
                campaign_id=campaign_id,
                gen=generation,
                variant_id=variant_id,
                parent=parent_dir.name,
                mutations=changes,
                fold_set=folds.VALIDATION_FOLDS_1H,
            )
            candidate.update(
                {
                    "mutation_name": "v72_effective_hunt",
                    "hunt": hunt,
                    "hunt_signature": signature,
                    "behavior_hash": behavior_hash(candidate),
                    "changes": changes,
                    "is_control": False,
                }
            )
            variants.append(candidate)
            with tried_path.open("a") as handle:
                handle.write(
                    json.dumps(
                        {
                            "campaign_id": campaign_id,
                            "generation": generation,
                            "id": variant_id,
                            "hunt_signature": signature,
                            "hunt": hunt,
                            "changes": changes,
                        },
                        default=str,
                    )
                    + "\n"
                )

        candidates = [control, *variants]
        behavior_seen = dict(known_behaviors)
        behavior_seen.setdefault(control["behavior_hash"], control["id"])
        unique = [control]
        for candidate in variants:
            bh = candidate["behavior_hash"]
            if bh in behavior_seen:
                candidate["no_op"] = True
                candidate["duplicate_of"] = behavior_seen[bh]
                candidate["rank_score"] = -999.0
                candidate["rank_confidence"] = 0.0
            else:
                candidate["no_op"] = False
                behavior_seen[bh] = candidate["id"]
                unique.append(candidate)

        for candidate in unique:
            known_behaviors.setdefault(candidate["behavior_hash"], candidate["id"])
        _atomic_json(behaviors_path, known_behaviors)

        rankings = rank_model_runs(
            {candidate["id"]: _fold_runs(candidate) for candidate in unique},
            min_trades=40,
            expected_runs=len(folds.VALIDATION_FOLDS_1H),
        )
        ranking_by_id = {row["id"]: row for row in rankings}
        for candidate in unique:
            row = ranking_by_id[candidate["id"]]
            candidate.update(
                {
                    "rank": row.get("rank"),
                    "rank_score": row.get("rank_score"),
                    "rank_confidence": row.get("rank_confidence"),
                    "failure_profile": row.get("failure_profile"),
                }
            )

        control_score = _rank_score(control)
        for candidate in candidates:
            score = _rank_score(candidate)
            delta = score - control_score
            candidate["champion_score"] = control_score
            candidate["score_delta_vs_champion"] = delta
            candidate["beat_champion"] = bool(
                not candidate.get("is_control")
                and not candidate.get("no_op")
                and delta >= 0.02
                and float(candidate.get("rank_confidence") or 0.0) >= 0.75
                and not (candidate.get("failure_profile") or {}).get("failure_tags")
            )
            candidate["evaluation_role"] = "selection_validation"

        selected = max(candidates, key=_rank_score)
        _atomic_json(
            generation_dir / "SEARCH_REPORT.json",
            {
                "campaign_id": campaign_id,
                "generation": generation,
                "cash": cash,
                "champion": {
                    "id": control["id"],
                    "rank_score": control_score,
                    "behavior_hash": control["behavior_hash"],
                },
                "selected": selected["id"],
                "selected_score": selected.get("rank_score"),
                "selected_delta_vs_champion": selected.get("score_delta_vs_champion"),
                "selected_beat_champion": selected.get("beat_champion"),
                "n_variants": len(variants),
                "n_behavioral_noops": sum(bool(row.get("no_op")) for row in variants),
                "candidates": [
                    {
                        "id": row["id"],
                        "rank_score": row.get("rank_score"),
                        "rank_confidence": row.get("rank_confidence"),
                        "no_op": row.get("no_op"),
                        "duplicate_of": row.get("duplicate_of"),
                        "score_delta_vs_champion": row.get("score_delta_vs_champion"),
                        "beat_champion": row.get("beat_champion"),
                        "hunt": row.get("hunt"),
                        "changes": row.get("changes", []),
                        "failure_profile": row.get("failure_profile"),
                    }
                    for row in candidates
                ],
                "honesty": {
                    "lockbox_opened": False,
                    "auto_promoted": False,
                    "behavioral_noops_rejected": True,
                    "champion_relative": True,
                },
            },
        )
        all_results.extend(candidates)
        parent_dir = Path(selected["model_dir"])

    return all_results
