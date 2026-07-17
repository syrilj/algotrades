from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from tools.evolve import v72_search


def _bundle(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / "signal_engine.py").write_text("class SignalEngine:\n    pass\n")
    (path / "config.json").write_text(
        json.dumps({"codes": ["SPY.US"], "interval": "1H", "strategy": {}})
    )
    (path / "hunt_config.json").write_text(
        json.dumps(
            {
                "sniper_model": "v71_live_confidence",
                "core_model": "v39d_confluence",
                "core_scale": 0.85,
                "both_core_frac": 0.35,
                "max_weight": 0.50,
                "sniper_min_conf": 0.0,
            }
        )
    )
    return path


def test_materialized_variant_changes_effective_hunt(tmp_path: Path):
    source = _bundle(tmp_path / "source")
    hunt = json.loads((source / "hunt_config.json").read_text())
    hunt["core_scale"] = 0.72
    dest = v72_search.materialize_variant(
        source,
        tmp_path / "candidate",
        hunt,
        parent_id="v72_dual_sleeve",
        changes=[{"parameter": "core_scale", "old": 0.85, "new": 0.72}],
    )
    assert json.loads((dest / "hunt_config.json").read_text())["core_scale"] == 0.72
    config = json.loads((dest / "config.json").read_text())
    assert config["strategy"]["promotion_eligible"] is False
    assert json.loads((dest / "MUTATION.json").read_text())["research_only"] is True


def test_behavior_hash_detects_same_and_different_realized_behavior():
    trades = pd.DataFrame(
        {
            "entry_time": pd.to_datetime(["2025-01-01"]),
            "exit_time": pd.to_datetime(["2025-01-02"]),
            "symbol": ["SPY.US"],
            "direction": [1],
            "entry_price": [100.0],
            "exit_price": [101.0],
            "size": [0.5],
            "pnl": [1.0],
        }
    )
    equity = pd.Series([1.0, 1.01], index=pd.date_range("2025-01-01", periods=2))
    first = {"trades": trades, "equity": equity}
    same = {"trades": trades.copy(), "equity": equity.copy()}
    different = {"trades": trades.assign(size=0.4), "equity": equity.copy()}
    assert v72_search.behavior_hash(first) == v72_search.behavior_hash(same)
    assert v72_search.behavior_hash(first) != v72_search.behavior_hash(different)


def test_campaign_rejects_behavioral_noops_and_keeps_control(tmp_path: Path, monkeypatch):
    champion = _bundle(tmp_path / "champion")
    monkeypatch.setattr(v72_search, "CHAMPION_DIR", champion)
    monkeypatch.setattr(v72_search, "_set_bridge", lambda _interval: None)

    def fake_run_candidate(model, **kwargs):
        fold_metrics = {
            name: {
                "ret": 0.10,
                "dd": -0.05,
                "sharpe": 1.2,
                "wr": 0.60,
                "pf": 1.5,
                "n": 10,
                "expectancy": 0.1,
            }
            for name in ("F1", "F2", "F3", "F4")
        }
        trades = pd.DataFrame(
            {
                "entry_time": pd.to_datetime(["2025-01-01"]),
                "exit_time": pd.to_datetime(["2025-01-02"]),
                "symbol": ["SPY.US"],
                "direction": [1],
                "entry_price": [100.0],
                "exit_price": [101.0],
                "size": [0.5],
                "pnl": [1.0],
            }
        )
        return {
            "id": kwargs["variant_id"],
            "variant_id": kwargs["variant_id"],
            "model_dir": str(model["model_dir"]),
            "parent": kwargs["parent"],
            "fold_metrics": fold_metrics,
            "fitness": 1.0,
            "trades": trades,
            "equity": pd.Series([1.0, 1.01], index=pd.date_range("2025-01-01", periods=2)),
            "codes": kwargs["codes"],
            "interval": "1H",
            "cash": kwargs["cash"],
        }

    monkeypatch.setattr(v72_search, "run_candidate", fake_run_candidate)
    results = v72_search.run_v72_campaign(
        champion,
        generations=1,
        cash=1_000,
        campaign_id="self_healing_c0001",
        memory_path=tmp_path / "run" / "MODEL_MEMORY.json",
        max_variants_per_generation=3,
    )
    control = next(row for row in results if row["is_control"])
    variants = [row for row in results if not row["is_control"]]
    assert len(variants) == 3
    assert all(row["no_op"] is True for row in variants)
    assert all(row["rank_score"] == -999.0 for row in variants)
    assert control["no_op"] is False
    report = json.loads(
        next((tmp_path / "run" / "v72_search").glob("**/SEARCH_REPORT.json")).read_text()
    )
    assert report["n_behavioral_noops"] == 3
    assert report["selected"] == control["id"]


def test_campaign_rejects_behavior_seen_in_prior_cycle(tmp_path: Path, monkeypatch):
    champion = _bundle(tmp_path / "champion")
    monkeypatch.setattr(v72_search, "CHAMPION_DIR", champion)
    monkeypatch.setattr(v72_search, "_set_bridge", lambda _interval: None)

    trades = pd.DataFrame(
        {
            "entry_time": pd.to_datetime(["2025-01-01"]),
            "exit_time": pd.to_datetime(["2025-01-02"]),
            "symbol": ["SPY.US"],
            "direction": [1],
            "entry_price": [100.0],
            "exit_price": [101.0],
            "size": [0.5],
            "pnl": [1.0],
        }
    )
    realized = {
        "trades": trades,
        "equity": pd.Series([1.0, 1.01], index=pd.date_range("2025-01-01", periods=2)),
    }
    behavior = v72_search.behavior_hash(realized)
    report_root = tmp_path / "run" / "v72_search"
    report_root.mkdir(parents=True)
    (report_root / "BEHAVIORS.json").write_text(json.dumps({behavior: "prior_candidate"}))

    def fake_run_candidate(model, **kwargs):
        return {
            **realized,
            "id": kwargs["variant_id"],
            "variant_id": kwargs["variant_id"],
            "model_dir": str(model["model_dir"]),
            "parent": kwargs["parent"],
            "fold_metrics": {
                name: {"ret": 0.1, "dd": -0.05, "sharpe": 1.2, "wr": 0.6, "pf": 1.5, "n": 10}
                for name in ("F1", "F2", "F3", "F4")
            },
            "fitness": 1.0,
            "codes": kwargs["codes"],
        }

    monkeypatch.setattr(v72_search, "run_candidate", fake_run_candidate)
    results = v72_search.run_v72_campaign(
        champion,
        campaign_id="self_healing_c0002",
        memory_path=tmp_path / "run" / "MODEL_MEMORY.json",
        max_variants_per_generation=1,
    )
    variant = next(row for row in results if not row["is_control"])
    assert variant["no_op"] is True
    assert variant["duplicate_of"] == "prior_candidate"
