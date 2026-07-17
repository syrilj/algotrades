from __future__ import annotations

import json
from pathlib import Path

from tools.self_healing_feedback_loop import LoopConfig, RunLock, SelfHealingLoop


def _model(tmp_path: Path) -> Path:
    model = tmp_path / "base"
    model.mkdir()
    (model / "signal_engine.py").write_text("class SignalEngine:\n    pass\n")
    (model / "config.json").write_text(
        json.dumps({"codes": ["SPY.US"], "interval": "1H", "strategy": {}})
    )
    return model


def _quality(path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ok": True}))
    return {"ok": True, "path": str(path)}


def _candidate(model: Path, score: float, candidate_id: str = "candidate") -> dict:
    return {
        "id": candidate_id,
        "parent": model.name,
        "model_dir": str(model),
        "rank_score": score,
        "fitness": score - 0.1,
        "rank": 1,
        "rank_confidence": 0.8,
        "failure_profile": {"failure_tags": []},
        "codes": ["SPY.US", "QQQ.US"],
        "interval": "1H",
        "extra_cfg": {"slippage_us": 0.0015},
        "evaluation_role": "selection_validation",
    }


def test_research_cycles_checkpoint_freeze_and_never_request_lockbox(tmp_path: Path):
    model = _model(tmp_path)
    calls: list[dict] = []

    def campaign(parent: Path, **kwargs):
        calls.append(kwargs)
        return [_candidate(parent, float(len(calls)), f"candidate_{len(calls)}")]

    config = LoopConfig(
        base_model=model.name,
        max_cycles=2,
        min_free_gb=0,
        retry_cooldown_seconds=0,
    )
    loop = SelfHealingLoop(config, tmp_path / "run", campaign_runner=campaign, quality_runner=_quality)
    state = loop._initial_state()
    state["current_parent_dir"] = str(model)
    loop._save(state)

    result = loop.run()

    assert result["status"] == "complete"
    assert result["cycles_completed"] == 2
    assert result["best_validation_score"] == 2.0
    assert all(call["qualify_generation_best"] is False for call in calls)
    frozen = Path(result["best_candidate"]["frozen_model_dir"])
    assert frozen.is_dir()
    config_json = json.loads((frozen / "config.json").read_text())
    assert config_json["codes"] == ["SPY.US", "QQQ.US"]
    assert config_json["strategy"]["promotion_eligible"] is False
    assert result["honesty"]["lockbox_used_for_learning"] is False


def test_edge_candidate_stops_remaining_research_cycles(tmp_path: Path):
    model = _model(tmp_path)
    calls = 0

    def campaign(parent: Path, **_kwargs):
        nonlocal calls
        calls += 1
        candidate = _candidate(parent, 0.8, "qualified_edge")
        candidate.update(
            {
                "beat_champion": True,
                "champion_score": 0.7,
                "score_delta_vs_champion": 0.1,
            }
        )
        return [candidate]

    loop = SelfHealingLoop(
        LoopConfig(base_model=model.name, max_cycles=5, min_free_gb=0),
        tmp_path / "run",
        campaign_runner=campaign,
        quality_runner=_quality,
    )
    state = loop._initial_state()
    state["current_parent_dir"] = str(model)
    loop._save(state)

    result = loop.run()

    assert calls == 1
    assert result["cycles_completed"] == 1
    assert result["status"] == "complete"
    assert result["stop_reason"] == "edge_candidate_found"
    assert result["edge_candidate"]["id"] == "qualified_edge"


def test_failed_cycle_recovers_then_succeeds(tmp_path: Path):
    model = _model(tmp_path)
    attempts = 0

    def campaign(parent: Path, **_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("transient backtest failure")
        return [_candidate(parent, 0.75)]

    config = LoopConfig(
        base_model=model.name,
        max_cycles=1,
        max_consecutive_failures=2,
        min_free_gb=0,
        retry_cooldown_seconds=0,
    )
    loop = SelfHealingLoop(config, tmp_path / "run", campaign_runner=campaign, quality_runner=_quality)
    state = loop._initial_state()
    state["current_parent_dir"] = str(model)
    loop._save(state)

    result = loop.run()

    assert attempts == 2
    assert result["status"] == "complete"
    assert result["cycles_completed"] == 1
    assert result["consecutive_failures"] == 0
    assert [row["status"] for row in result["history"]] == ["failed", "completed"]


def test_failure_budget_fails_closed(tmp_path: Path):
    model = _model(tmp_path)

    def campaign(_parent: Path, **_kwargs):
        raise RuntimeError("persistent failure")

    config = LoopConfig(
        base_model=model.name,
        max_cycles=1,
        max_consecutive_failures=2,
        min_free_gb=0,
        retry_cooldown_seconds=0,
    )
    loop = SelfHealingLoop(config, tmp_path / "run", campaign_runner=campaign, quality_runner=_quality)
    state = loop._initial_state()
    state["current_parent_dir"] = str(model)
    loop._save(state)

    result = loop.run()

    assert result["status"] == "failed"
    assert result["cycles_completed"] == 0
    assert result["stop_reason"] == "consecutive_failure_budget_exhausted"


def test_stop_file_stops_before_research(tmp_path: Path):
    model = _model(tmp_path)
    called = False

    def campaign(_parent: Path, **_kwargs):
        nonlocal called
        called = True
        return []

    loop = SelfHealingLoop(
        LoopConfig(base_model=model.name, min_free_gb=0),
        tmp_path / "run",
        campaign_runner=campaign,
        quality_runner=_quality,
    )
    state = loop._initial_state()
    state["current_parent_dir"] = str(model)
    loop._save(state)
    loop.stop_path.write_text("stop\n")

    result = loop.run()

    assert result["status"] == "stopped"
    assert result["stop_reason"] == "stop_requested"
    assert called is False


def test_terminal_qualification_runs_only_after_learning_stops(tmp_path: Path, monkeypatch):
    model = _model(tmp_path)

    def campaign(parent: Path, **kwargs):
        assert kwargs["qualify_generation_best"] is False
        return [_candidate(parent, 1.0)]

    loop = SelfHealingLoop(
        LoopConfig(
            base_model=model.name,
            max_cycles=1,
            min_free_gb=0,
            retry_cooldown_seconds=0,
            qualify_final=True,
        ),
        tmp_path / "run",
        campaign_runner=campaign,
        quality_runner=_quality,
    )
    state = loop._initial_state()
    state["current_parent_dir"] = str(model)
    loop._save(state)
    seen: list[str] = []

    def qualify(state: dict, frozen: Path) -> dict:
        seen.append(state["status"])
        assert frozen.is_dir()
        return {"status": "COMPLETED", "fed_back_into_learning": False}

    monkeypatch.setattr(loop, "_qualify_once", qualify)
    result = loop.run()

    assert seen == ["qualifying"]
    assert result["qualification"]["fed_back_into_learning"] is False
    assert result["status"] == "complete"


def test_terminal_qualification_failure_is_checkpointed(tmp_path: Path, monkeypatch):
    model = _model(tmp_path)

    def campaign(parent: Path, **_kwargs):
        return [_candidate(parent, 1.0)]

    loop = SelfHealingLoop(
        LoopConfig(
            base_model=model.name,
            max_cycles=1,
            min_free_gb=0,
            retry_cooldown_seconds=0,
            qualify_final=True,
        ),
        tmp_path / "run",
        campaign_runner=campaign,
        quality_runner=_quality,
    )
    state = loop._initial_state()
    state["current_parent_dir"] = str(model)
    loop._save(state)
    monkeypatch.setattr(
        loop, "_qualify_once", lambda *_args: (_ for _ in ()).throw(RuntimeError("gate broke"))
    )

    result = loop.run()

    assert result["status"] == "failed"
    assert result["stop_reason"] == "terminal_qualification_failed"
    assert result["qualification"]["status"] == "FAILED"
    assert result["qualification"]["fed_back_into_learning"] is False


def test_missing_base_fails_closed_in_checkpoint(tmp_path: Path):
    loop = SelfHealingLoop(
        LoopConfig(base_model="missing", min_free_gb=0),
        tmp_path / "run",
        campaign_runner=lambda *_args, **_kwargs: [],
        quality_runner=_quality,
    )
    result = loop.run()
    assert result["status"] == "failed"
    assert result["stop_reason"].startswith("base_model_incomplete:")
    assert json.loads(loop.state_path.read_text())["pid"] is None


def test_run_lock_recovers_stale_pid(tmp_path: Path):
    path = tmp_path / "RUN.lock"
    path.write_text("99999999")
    with RunLock(path):
        assert int(path.read_text()) > 0
    assert not path.exists()
