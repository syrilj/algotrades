"""Auto model selection must not brick the decision engine.

An engine that cannot clear the active-calibration gate always ABSTAINs with
execution_blocked, so picking it over a calibratable engine turns the whole
decision pipeline into a dead WAIT (the TSLA/v50_high_win_rate incident).
Selection prefers the highest-confidence engine *that can actually be sized*;
when no candidate is calibratable it keeps legacy behavior (analysis still
renders, gate still fails closed).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import confidence_runtime as cr  # noqa: E402
import model_registry as mr  # noqa: E402


def _fake_route(symbol, desk_only=True, horizon=None, **kw):
    return {
        "model": "v50_high_win_rate",
        "score": 1.0,
        "candidates": [
            {"model": "v50_high_win_rate", "final_score": 1.0},
            {"model": "v71_live_confidence", "final_score": 0.8},
        ],
        "router_confidence": {"value": 0.6, "band": "medium"},
        "track": "standard",
        "code": "TSLA.US",
    }


def _probe(symbol, model):
    # v50 probes slightly stronger — selection must still refuse it when
    # only v71 can clear the calibration gate.
    raw = 0.72 if model == "v50_high_win_rate" else 0.66
    return {"ok": True, "raw_probability": raw, "setup_ok": True}


def test_selection_prefers_calibratable_engine(monkeypatch):
    monkeypatch.setattr(mr, "route_best_model", _fake_route)
    monkeypatch.setattr(
        cr,
        "load_active_calibrator",
        lambda model, path=None: {"available": model == "v71_live_confidence"},
    )
    sel = mr.select_model_for_confidence("TSLA", horizon="swing", probe_fn=_probe)
    assert sel["model"] == "v71_live_confidence"
    assert sel["calibration_available"] is True
    by_model = {p["model"]: p for p in sel["probes"]}
    assert by_model["v50_high_win_rate"]["calibration_available"] is False
    assert by_model["v71_live_confidence"]["calibration_available"] is True


def test_calibratable_candidate_rescued_past_probe_cap(monkeypatch):
    # v71 sits below the probe cutoff; it must still be pulled into the pool
    # when nothing above the cutoff can clear the calibration gate.
    monkeypatch.setattr(mr, "route_best_model", _fake_route)
    monkeypatch.setattr(
        cr,
        "load_active_calibrator",
        lambda model, path=None: {"available": model == "v71_live_confidence"},
    )
    sel = mr.select_model_for_confidence(
        "TSLA", horizon="swing", max_probe=1, probe_fn=_probe
    )
    assert sel["model"] == "v71_live_confidence"
    assert sel["calibration_available"] is True


def test_selection_falls_back_when_nothing_calibratable(monkeypatch):
    monkeypatch.setattr(mr, "route_best_model", _fake_route)
    monkeypatch.setattr(
        cr, "load_active_calibrator", lambda model, path=None: {"available": False}
    )
    sel = mr.select_model_for_confidence("TSLA", horizon="swing", probe_fn=_probe)
    # Legacy behavior: best conf_score wins; caller sees the gate is closed.
    assert sel["model"] == "v50_high_win_rate"
    assert sel["calibration_available"] is False
