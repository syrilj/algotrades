from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import dynamic_model_rank as dmr


@pytest.fixture
def isolated_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "workspace"
    model_dir = root / "model"
    model_dir.mkdir(parents=True)
    (model_dir / "signal_engine.py").write_text("MODEL_VALUE = 1\n")
    (model_dir / "helper.py").write_text("HELPER_VALUE = 1\n")
    (model_dir / "config.json").write_text(json.dumps({"interval": "1H"}))
    (model_dir / "DEPENDENCIES.json").write_text(
        json.dumps(
            {
                "files": [
                    {"source": "helper.py", "target": "vendor/helper.py"},
                ]
            }
        )
    )
    model = {
        "id": "test_adaptive_model",
        "src_dir": model_dir,
        "model_dir": model_dir,
        "interval": "1H",
    }
    calls: list[dict] = []

    def fake_backtest(run_dir: Path) -> None:
        calls.append(json.loads((run_dir / "config.json").read_text()))
        artifacts = run_dir / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        (artifacts / "metrics.csv").write_text(
            "total_return,max_drawdown,sharpe,trade_count,win_rate,final_value\n"
            "0.25,-0.10,1.5,12,0.75,1250\n"
        )

    monkeypatch.setattr(dmr, "ROOT", root)
    monkeypatch.setattr(dmr, "OUT", root / "rank_output")
    monkeypatch.setattr(dmr, "bt_main", fake_backtest)
    return model, model_dir, calls


def _request(model: dict, **overrides):
    kwargs = {
        "mode": "daily",
        "codes": ["SPY.US", "QQQ.US"],
        "start": "2025-01-01",
        "end": "2025-06-30",
        "tag": "contract_test",
        "force_1d": False,
        "reuse": True,
        "cash": 1000,
        "source": "local",
        "interval": "1H",
        "extra_cfg": {"nested": {"a": 1, "b": 2}},
    }
    kwargs.update(overrides)
    return dmr.run_one(model, **kwargs)


def test_run_one_persists_full_contract_and_reuses_only_exact_match(isolated_runner):
    model, _model_dir, calls = isolated_runner

    first = _request(model)
    second = _request(model, extra_cfg={"nested": {"b": 2, "a": 1}})

    assert first["reused"] is False
    assert second["reused"] is True
    assert len(calls) == 1

    contract_path = (
        dmr.OUT
        / "runs"
        / model["id"]
        / "contract_test__daily__c1000"
        / "request_contract.json"
    )
    contract = json.loads(contract_path.read_text())
    assert contract["model_id"] == model["id"]
    assert contract["codes"] == ["SPY.US", "QQQ.US"]
    assert contract["start"] == "2025-01-01"
    assert contract["end"] == "2025-06-30"
    assert contract["source"] == "local"
    assert contract["interval"] == "1H"
    assert contract["mode"] == "daily"
    assert contract["cash"] == 1000.0
    assert contract["extra_cfg"] == {"nested": {"a": 1, "b": 2}}
    hashes = contract["model_source_dependency_hashes"]
    assert {row["target"] for row in hashes} >= {
        "signal_engine.py",
        "config.json",
        "DEPENDENCIES.json",
        "vendor/helper.py",
    }
    assert all(len(row["sha256"]) == 64 for row in hashes)


@pytest.mark.parametrize(
    "override",
    [
        {"codes": ["QQQ.US", "SPY.US"]},
        {"start": "2025-01-02"},
        {"end": "2025-06-29"},
        {"source": "yfinance"},
        {"interval": "1D"},
        {"extra_cfg": {"nested": {"a": 1, "b": 3}}},
        {"extra_cfg": {"nested": {"a": 1.0, "b": 2}}},
    ],
)
def test_request_contract_mismatch_invalidates_run_reuse(isolated_runner, override):
    model, _model_dir, calls = isolated_runner
    _request(model)

    result = _request(model, **override)

    assert result["reused"] is False
    assert len(calls) == 2


@pytest.mark.parametrize("changed_file", ["signal_engine.py", "helper.py"])
def test_model_or_declared_dependency_change_invalidates_run_reuse(
    isolated_runner,
    changed_file: str,
):
    model, model_dir, calls = isolated_runner
    _request(model)
    (model_dir / changed_file).write_text("CHANGED = True\n")

    result = _request(model)

    assert result["reused"] is False
    assert len(calls) == 2


def test_legacy_metrics_without_contract_are_not_reused(isolated_runner):
    model, _model_dir, calls = isolated_runner
    first = _request(model)
    (dmr.ROOT / first["path"] / "request_contract.json").unlink()

    result = _request(model)

    assert result["reused"] is False
    assert len(calls) == 2


def test_failed_run_does_not_publish_reusable_contract(
    isolated_runner,
    monkeypatch: pytest.MonkeyPatch,
):
    model, _model_dir, _calls = isolated_runner

    def fail_backtest(_run_dir: Path) -> None:
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(dmr, "bt_main", fail_backtest)
    result = _request(model)

    assert result["error"] == "synthetic failure"
    assert not (dmr.ROOT / result["path"] / "request_contract.json").exists()


def test_explicit_causal_execution_is_model_independent_and_ac_takes_precedence(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(dmr._runner, "_detect_market", lambda _code: "us_equity")
    monkeypatch.setattr(dmr._runner, "_detect_submarket", lambda _codes: "us")
    monkeypatch.setattr(
        dmr,
        "CausalGlobalEquityEngine",
        lambda config, market: ("causal", config, market),
    )
    monkeypatch.setattr(
        dmr,
        "AlmgrenChrissGlobalEquityEngine",
        lambda config, market: ("ac", config, market),
    )
    monkeypatch.setattr(
        dmr,
        "GlobalEquityEngine",
        lambda config, market: ("global", config, market),
    )
    monkeypatch.setattr(
        dmr,
        "_original_create_market_engine",
        lambda source, config, codes: ("original", source, config, codes),
    )

    custom = {"causal_execution": True, "strategy": {"model_version": "custom"}}
    assert dmr._create_market_engine_for_local("yfinance", custom, ["SPY.US"])[0] == "causal"

    with_impact = {**custom, "impact_model": "almgren_chriss"}
    assert dmr._create_market_engine_for_local("local", with_impact, ["SPY.US"])[0] == "ac"

    legacy = {"strategy": {"model_version": "v48_regime_barbell"}}
    assert dmr._create_market_engine_for_local("local", legacy, ["SPY.US"])[0] == "causal"

    ordinary = {"strategy": {"model_version": "custom"}}
    assert dmr._create_market_engine_for_local("local", ordinary, ["SPY.US"])[0] == "global"
    assert dmr._create_market_engine_for_local("yfinance", ordinary, ["SPY.US"])[0] == "original"
