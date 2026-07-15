from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from evolve.model_feedback import (  # noqa: E402
    diagnose_model,
    empty_memory,
    load_memory,
    prioritize_mutation_menu,
    rank_model_runs,
    record_generation,
)
from evolve.mutations import spawn_mutations  # noqa: E402


def _row(tag: str, utility: float, *, ret: float = 0.1, dd: float = -0.1, sharpe: float = 1.0, n: int = 20):
    return {
        "tag": tag,
        "utility": utility,
        "ret": ret,
        "dd": dd,
        "sharpe": sharpe,
        "wr": 0.55,
        "n": n,
        "mode": "daily",
        "data_track": "equity_ohlcv",
    }


def test_robust_rank_prefers_stable_model_over_spiky_mean():
    ranked = rank_model_runs(
        {
            "steady": [_row("fold_1", 1.0), _row("fold_2", 0.9)],
            "spiky": [
                _row("train", 2.5, ret=0.5, sharpe=2.5),
                _row("oos", -0.3, ret=-0.1, sharpe=-0.4),
            ],
        },
        expected_runs=2,
    )

    assert ranked[0]["id"] == "steady"
    assert ranked[0]["rank_confidence"] == 1.0
    spiky = next(row for row in ranked if row["id"] == "spiky")
    assert "oos_degradation" in spiky["failure_profile"]["failure_tags"]
    assert spiky["rank_components"]["stability_penalty"] > 0
    assert spiky["rank_components"]["oos_penalty"] > 0


def test_diagnosis_records_evidence_and_actions():
    profile = diagnose_model(
        "broken",
        [_row("oos", -1.0, ret=-0.2, dd=-0.31, sharpe=-0.5, n=8)],
    )

    assert profile["status"] == "FAIL"
    assert {"thin_sample", "negative_return", "weak_sharpe", "hard_drawdown"}.issubset(
        profile["failure_tags"]
    )
    hard_dd = next(item for item in profile["failures"] if item["tag"] == "hard_drawdown")
    assert "drawdown=0.310" in hard_dd["evidence"]
    assert "Reduce position risk" in hard_dd["action"]


def test_memory_learns_mutation_delta_and_prioritizes_matching_fix(tmp_path: Path):
    memory_path = tmp_path / "MODEL_MEMORY.json"
    parent = {
        **_row("screen", 0.5, dd=-0.30, n=50),
        "id": "parent",
        "rank_score": 0.5,
        "rank_confidence": 1.0,
    }
    parent["failure_profile"] = diagnose_model("parent", [parent])
    child = {
        **_row("screen", 0.8, dd=-0.12, n=50),
        "id": "child",
        "rank_score": 0.8,
        "rank_confidence": 1.0,
        "parent": "parent",
        "mutation_name": "tight_risk",
    }
    child["failure_profile"] = diagnose_model("child", [child])

    record_generation(
        [child, parent],
        generation=1,
        parent_scores={"parent": 0.5},
        path=memory_path,
    )
    memory = load_memory(memory_path)
    assert memory["mutations"]["tight_risk"]["attempts"] == 1
    assert memory["mutations"]["tight_risk"]["wins"] == 1
    assert abs(memory["mutations"]["tight_risk"]["mean_delta"] - 0.3) < 1e-12

    menu = [
        {"name": "random_change", "targets": ["thin_sample"]},
        {"name": "tight_risk", "targets": ["hard_drawdown"]},
    ]
    prioritized = prioritize_mutation_menu(menu, [parent["failure_profile"]], memory)
    assert prioritized[0]["name"] == "tight_risk"
    assert prioritized[0]["feedback_reason"]["matched_failures"]["hard_drawdown"] > 0

    raw = json.loads(memory_path.read_text())
    assert raw["schema_version"] == 1
    assert raw["generations"][0]["best_id"] == "child"


def test_mutation_budget_is_distributed_across_elite_parents(tmp_path: Path):
    def model(name: str) -> dict:
        model_dir = tmp_path / name
        model_dir.mkdir()
        (model_dir / "config.json").write_text(json.dumps({"engine": "daily"}))
        (model_dir / "signal_engine.py").write_text("# stub\n")
        return {
            "id": name,
            "src_dir": model_dir,
            "model_dir": model_dir,
            "modes": ["daily"],
            "has_hunt": False,
        }

    parents = [model("elite_a"), model("elite_b")]
    menu = [
        {"name": "first", "applies": "equity", "config": {"commission": 0.001}},
        {"name": "second", "applies": "equity", "config": {"commission": 0.002}},
    ]
    spawned = spawn_mutations(parents, tmp_path / "mutations", max_mutations=2, menu=menu)

    assert {mutation["parent"] for mutation in spawned} == {"elite_a", "elite_b"}
    assert {mutation["mutation_name"] for mutation in spawned} == {"first"}


def test_empty_memory_has_stable_schema():
    memory = empty_memory()
    assert memory["schema_version"] == 1
    assert memory["models"] == {}
    assert memory["mutations"] == {}
