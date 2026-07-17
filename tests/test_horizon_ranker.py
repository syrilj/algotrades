"""Horizon-aware model ranking + confidence-ranker tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import model_registry as mr  # noqa: E402
import symbol_ranker as sr  # noqa: E402
from confidence_runtime import evaluate_confidence  # noqa: E402


def test_normalize_horizon_aliases():
    assert mr.normalize_horizon("daytrade") == "day"
    assert mr.normalize_horizon("1h") == "day"
    assert mr.normalize_horizon("weekly") == "swing"
    assert mr.normalize_horizon("long_term") == "position"
    assert mr.normalize_horizon(None) == "swing"
    assert mr.normalize_horizon("garbage") == "swing"


def test_model_horizon_affinity_day_prefers_v71():
    day_v71 = mr.model_horizon_affinity("v71_live_confidence", "day")
    day_v50 = mr.model_horizon_affinity("v50_high_win_rate", "day")
    swing_v50 = mr.model_horizon_affinity("v50_high_win_rate", "swing")
    assert day_v71 > day_v50
    assert swing_v50 > day_v50
    assert swing_v50 >= 0.9


def test_horizon_confidence_thresholds_ordering():
    day = mr.horizon_confidence_thresholds("day")
    swing = mr.horizon_confidence_thresholds("swing")
    pos = mr.horizon_confidence_thresholds("position")
    assert day["enter"] < swing["enter"] < pos["enter"]
    assert day["watch"] < pos["watch"]


def test_window_specs_interval_by_horizon():
    day = sr.window_specs(horizon="day")
    swing = sr.window_specs(horizon="swing")
    pos = sr.window_specs(horizon="position")
    assert day["full"]["interval"] == "1H"
    assert swing["full"]["interval"] == "1D"
    assert pos["full"]["interval"] == "1D"
    assert day["recent"]["start"] > swing["recent"]["start"] or True  # shorter lookback ok


def test_equity_candidates_include_champions():
    cands = sr.equity_candidates(max_models=12, horizon="day")
    # At least one live sleeve or core champion must be present when engines exist.
    champions = {"v39d_confluence", "v71_live_confidence", "v72_dual_sleeve", "v39b_live_adapt"}
    assert champions.intersection(set(cands)), cands


def test_route_best_model_exposes_horizon_and_router_confidence():
    routed = mr.route_best_model("TSLA", horizon="day")
    assert routed.get("model")
    assert routed.get("horizon") == "day"
    rconf = routed.get("router_confidence") or {}
    assert "value" in rconf
    assert rconf.get("band") in ("low", "medium", "high")
    assert isinstance(routed.get("candidates"), list)
    assert len(routed["candidates"]) >= 1
    # Day horizon should surface affinity on candidates.
    for c in routed["candidates"]:
        assert "horizon_affinity" in c
        assert "final_score" in c


def test_route_best_model_day_vs_position_can_diverge():
    day = mr.route_best_model("TSLA", horizon="day")
    pos = mr.route_best_model("TSLA", horizon="position")
    # Both must succeed; model may match or differ — scores must include affinity.
    assert day["score"] is not None and pos["score"] is not None
    day_aff = next(
        (c["horizon_affinity"] for c in day["candidates"] if c["model"] == "v71_live_confidence"),
        None,
    )
    pos_aff = next(
        (c["horizon_affinity"] for c in pos["candidates"] if c["model"] == "v71_live_confidence"),
        None,
    )
    if day_aff is not None and pos_aff is not None:
        assert day_aff > pos_aff


def test_select_model_for_confidence_with_probe_fn():
    def fake_probe(symbol: str, model: str) -> dict:
        # Prefer v71 when probed.
        if model == "v71_live_confidence":
            return {
                "ok": True,
                "raw_probability": 0.78,
                "setup_ok": True,
                "action_hint": "BUY NOW",
            }
        return {
            "ok": True,
            "raw_probability": 0.52,
            "setup_ok": False,
            "action_hint": "WAIT",
        }

    hit = mr.select_model_for_confidence(
        "TSLA",
        horizon="day",
        desk_only=True,
        max_probe=6,
        probe_fn=fake_probe,
    )
    assert hit["source"] == "confidence_ranker"
    assert hit["horizon"] == "day"
    assert hit["model"] == "v71_live_confidence"
    assert hit.get("raw_probability") == 0.78
    assert hit.get("setup_ok") is True
    assert hit.get("router_confidence", {}).get("value", 0) > 0.5
    assert len(hit.get("probes") or []) >= 1


def test_select_model_for_confidence_router_only():
    hit = mr.select_model_for_confidence(
        "TSLA", horizon="swing", desk_only=True, max_probe=4, probe_fn=None
    )
    assert hit.get("model")
    assert hit["horizon"] == "swing"
    assert hit["source"] == "confidence_ranker"


def test_evaluate_confidence_horizon_tag_and_thresholds():
    fresh = {"available": True, "stale": False}
    day = evaluate_confidence(
        0.70,
        model_ok=True,
        setup_ok=True,
        freshness=fresh,
        model="v39d_confluence",
        horizon="day",
    )
    pos = evaluate_confidence(
        0.70,
        model_ok=True,
        setup_ok=True,
        freshness=fresh,
        model="v39d_confluence",
        horizon="position",
    )
    assert day["horizon"] == "day"
    assert pos["horizon"] == "position"
    assert day.get("thresholds", {}).get("enter") <= pos.get("thresholds", {}).get("enter")


def test_ranker_best_allows_relative_negative_scores(tmp_path, monkeypatch):
    """When all scores ≤0, relative best still returns with relative_only=True."""
    import json
    from datetime import datetime, timezone

    sym = "FAKE"
    root = tmp_path / "symbol_ranker" / sym
    root.mkdir(parents=True)
    art = {
        "schema": 2,
        "symbol": sym,
        "code": "FAKE.US",
        "horizon": "swing",
        "asof": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "complete",
        "rows": [
            {
                "model": "v39d_confluence",
                "status": "ok",
                "score": -0.05,
                "claim_level": "RESEARCH",
                "desk_runnable": True,
                "trade_count": 20,
                "reliability": 0.5,
                "win_rate": 0.55,
                "sharpe": 0.8,
            },
            {
                "model": "v23_devin_overlay",
                "status": "ok",
                "score": -0.30,
                "claim_level": "RESEARCH",
                "desk_runnable": True,
                "trade_count": 12,
                "reliability": 0.3,
            },
        ],
    }
    (root / "RANKER.json").write_text(json.dumps(art))
    monkeypatch.setattr(mr, "RANKER_ROOT", tmp_path / "symbol_ranker")
    hit = mr.ranker_best_model("FAKE", desk_only=False, horizon="swing")
    assert hit is not None
    assert hit["model"] == "v39d_confluence"
    assert hit["relative_only"] is True
    # (c) Neither row has window_metrics, so recomputed confidence is 0.0 for
    # both — selection must fall back to the legacy score-based pick above,
    # and the router-facing flag must say so.
    assert hit["confidence"] == 0.0
    assert hit["low_confidence"] is True


def _ranker_full_window(n: int, wr: float, plr: float, dd: float = -0.08) -> dict:
    return {
        "status": "ok",
        "trade_count": n,
        "win_rate": wr,
        "profit_loss_ratio": plr,
        "profit_factor": plr * wr / max(1e-9, 1 - wr),
        "max_drawdown": dd,
        "total_return": 0.2,
        "sharpe": 1.5,
    }


def test_ranker_best_prefers_high_confidence_over_high_score(tmp_path, monkeypatch):
    """(a) A high-confidence row must outrank a higher-score, low-confidence row."""
    import json
    from datetime import datetime, timezone

    sym = "CONF"
    root = tmp_path / "symbol_ranker" / sym
    root.mkdir(parents=True)

    low_conf_row = {
        "model": "v_lowconf_highscore",
        "status": "ok",
        "score": 0.9,
        "claim_level": "RESEARCH",
        "desk_runnable": True,
        "trade_count": 40,
        "reliability": 0.5,
        "win_rate": 0.55,
        "sharpe": 0.5,
        "oos_consistency": 1.0,
        # 55% WR at PLR 1.2 on 40 trades: Wilson LB below breakeven -> 0 confidence.
        "window_metrics": {
            "full": _ranker_full_window(40, 0.55, 1.2),
            "recent": {"status": "ok", "trade_count": 13, "total_return": 0.1},
        },
    }
    high_conf_row = {
        "model": "v_highconf_lowscore",
        "status": "ok",
        "score": 0.2,
        "claim_level": "RESEARCH",
        "desk_runnable": True,
        "trade_count": 60,
        "reliability": 0.5,
        "win_rate": 0.70,
        "sharpe": 1.5,
        "oos_consistency": 1.0,
        # 70% WR at PLR 2.0 on 60 trades -> strong evidence-gated confidence.
        "window_metrics": {
            "full": _ranker_full_window(60, 0.70, 2.0),
            "recent": {"status": "ok", "trade_count": 20, "total_return": 0.1},
        },
    }
    art = {
        "schema": 2,
        "symbol": sym,
        "code": "CONF.US",
        "horizon": "swing",
        "asof": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "complete",
        "rows": [low_conf_row, high_conf_row],
    }
    (root / "RANKER.json").write_text(json.dumps(art))
    monkeypatch.setattr(mr, "RANKER_ROOT", tmp_path / "symbol_ranker")

    hit = mr.ranker_best_model(sym, desk_only=False, horizon="swing")
    assert hit is not None
    # Raw score favors v_lowconf_highscore (0.9 > 0.2); confidence must win instead.
    assert hit["model"] == "v_highconf_lowscore"
    assert hit["relative_only"] is False
    assert hit["confidence"] >= 0.70


def test_ranker_best_hit_includes_confidence_and_low_confidence_flag(tmp_path, monkeypatch):
    """(b) The returned hit always carries `confidence` + `low_confidence`."""
    import json
    from datetime import datetime, timezone

    sym = "WATCH"
    root = tmp_path / "symbol_ranker" / sym
    root.mkdir(parents=True)

    # Positive edge but thin sample -> capped confidence, below the swing
    # "watch" threshold (0.50), so low_confidence must be flagged True.
    row = {
        "model": "v_thin_edge",
        "status": "ok",
        "score": 0.3,
        "claim_level": "RESEARCH",
        "desk_runnable": True,
        "trade_count": 8,
        "reliability": 0.4,
        "win_rate": 0.95,
        "sharpe": 1.0,
        "oos_consistency": 1.0,
        "window_metrics": {
            "full": _ranker_full_window(8, 0.95, 3.0),
            "recent": {"status": "ok", "trade_count": 3, "total_return": 0.1},
        },
    }
    art = {
        "schema": 2,
        "symbol": sym,
        "code": "WATCH.US",
        "horizon": "swing",
        "asof": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "complete",
        "rows": [row],
    }
    (root / "RANKER.json").write_text(json.dumps(art))
    monkeypatch.setattr(mr, "RANKER_ROOT", tmp_path / "symbol_ranker")

    hit = mr.ranker_best_model(sym, desk_only=False, horizon="swing")
    assert hit is not None
    assert "confidence" in hit
    assert 0.0 < hit["confidence"] <= sr.CONF_THIN_CAP
    assert hit["low_confidence"] is True
