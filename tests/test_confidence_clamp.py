from __future__ import annotations

import math
from unittest.mock import patch

import pytest

from tools.confidence_runtime import ORDINAL_CONFIDENCE_CAP, clamp_ordinal_confidence


# ---------------------------------------------------------------------------
# Unit tests for the shared helper (P0-4).
# ---------------------------------------------------------------------------


def test_clamp_caps_uncalibrated_values_above_cap():
    assert clamp_ordinal_confidence(0.90) == pytest.approx(0.75)
    assert clamp_ordinal_confidence(0.999) == pytest.approx(0.75)
    assert clamp_ordinal_confidence(1.0) == pytest.approx(0.75)


def test_clamp_passes_through_values_at_or_below_cap():
    assert clamp_ordinal_confidence(0.75) == pytest.approx(0.75)
    assert clamp_ordinal_confidence(0.5) == pytest.approx(0.5)
    assert clamp_ordinal_confidence(0.0) == pytest.approx(0.0)


def test_clamp_respects_custom_cap():
    assert clamp_ordinal_confidence(0.90, cap=0.60) == pytest.approx(0.60)
    assert clamp_ordinal_confidence(0.50, cap=0.60) == pytest.approx(0.50)


def test_clamp_default_cap_matches_module_constant():
    assert ORDINAL_CONFIDENCE_CAP == pytest.approx(0.75)


def test_clamp_is_a_noop_when_probability_calibrated():
    # A real cross-fitted calibrator's output must pass through unchanged —
    # the cap only guards ordinal (non-probability) scores.
    assert clamp_ordinal_confidence(0.92, probability_calibrated=True) == pytest.approx(0.92)
    assert clamp_ordinal_confidence(0.30, probability_calibrated=True) == pytest.approx(0.30)


def test_clamp_none_in_none_out():
    assert clamp_ordinal_confidence(None) is None


def test_clamp_non_finite_input_returns_none():
    assert clamp_ordinal_confidence(float("nan")) is None
    assert clamp_ordinal_confidence(float("inf")) is None


def test_clamp_rejects_unparseable_input():
    assert clamp_ordinal_confidence("not-a-number") is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Wiring: trade_desk._compute_state's serving boundary clamps confidence
# fields (P0-4 "surfaced to plans/UI").
# ---------------------------------------------------------------------------


def test_trade_desk_clamps_confidence_at_serving_boundary():
    import trade_desk

    # trade_desk._compute_state always routes its "confidence" /
    # "hit_probability" / "engine_confidence" fields through
    # clamp_ordinal_confidence before returning — assert the source wires it
    # in rather than re-deriving every branch of the desk math here (that is
    # covered indirectly by the existing trade_desk tests).
    import inspect

    source = inspect.getsource(trade_desk._compute_state)
    assert "clamp_ordinal_confidence" in source
    assert '"confidence": clamp_ordinal_confidence' in source
    assert '"hit_probability": clamp_ordinal_confidence' in source
    assert '"engine_confidence": clamp_ordinal_confidence' in source


# ---------------------------------------------------------------------------
# End-to-end: a plan/draft built from a 0.9-confidence signal reports <= 0.75.
# ---------------------------------------------------------------------------


class _StubLiveSignalEngine:
    """Deterministic, offline stand-in for services.live_signal.LiveSignalEngine."""

    def analyze(self, symbol: str, df=None):
        return {
            "symbol": symbol,
            "go_long": True,
            "soft_long": True,
            "go_short": False,
            "soft_short": False,
            "confidence": 0.95,  # raw live-feature ordinal score, also high
            "confidence_bear": 0.05,
            "vol_z": 2.0,
            "atr_pct": 0.02,
            "above_vwap": True,
            "swing_uptrend": True,
            "macd_positive": True,
            "price": 100.0,
            "timestamp": "2026-07-16T15:00:00Z",
            "signal_strength": 10.0,
            "signal_strength_bear": 0.0,
            "error": None,
        }


def _stub_macro_regime(adapter=None):
    return {
        "qqq_trend": "up",
        "qqq_ok": True,
        "xlp_spy_ratio_state": "risk_on",
        "macro_ok": True,
        "error": None,
    }


def _stub_try_model_confidence(symbol, model=None):
    # This is the injection point for the "0.9-confidence signal" scenario:
    # a v72-shaped ordinal score in the unsupported 0.85-0.95 band, exactly
    # like the final-holdout top reliability bin the plan flags as
    # untrustworthy (event_rate 0.25 at mean_probability ~0.90).
    return {
        "ok": True,
        "model": model or "v72_dual_sleeve",
        "confidence": 0.90,
        "raw_probability": 0.90,
        "raw_probability_source": "trade_desk_hit_probability",
        "setup_ok": True,
        "price": 100.0,
        "entry": 100.0,
        "stop": 95.0,
        "action_hint": "BUY NOW",
        "flags": {},
    }


def test_plan_symbol_reports_clamped_confidence_end_to_end(tmp_path, monkeypatch):
    import live_plan

    monkeypatch.setattr(live_plan, "LiveSignalEngine", _StubLiveSignalEngine)
    monkeypatch.setattr(live_plan, "macro_regime", _stub_macro_regime)
    monkeypatch.setattr(live_plan, "try_model_confidence", _stub_try_model_confidence)
    monkeypatch.setattr(
        live_plan,
        "options_propose",
        lambda *a, **k: {"action": "skip", "reason": "test stub", "attack_path": False},
    )
    # No real calibrator artifact is exercised here — force ABSTAIN so the
    # execution gate stays fail-closed regardless of fixture drift, while the
    # *displayed* ordinal confidence is still what's under test.
    monkeypatch.setattr(
        live_plan,
        "load_active_calibrator",
        lambda *a, **k: {"available": False, "reason": "test_stub_no_calibrator"},
    )
    monkeypatch.setattr("gamma_exposure.compute_gamma_exposure", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no network in tests")))
    monkeypatch.setattr("live_adapt.size_mult_for", lambda *a, **k: 1.0)
    monkeypatch.setattr("live_adapt.snapshot", lambda *a, **k: {"ok": True})
    monkeypatch.setattr("live_adapt.export_ib_ticket", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(live_plan.ShadowDecisionLedger, "record", lambda self, payload: "test-event-id")
    monkeypatch.setattr(live_plan, "_production_lse_only", lambda: False)

    out = live_plan.plan_symbol(
        "TSLA",
        account=1000.0,
        peak=1000.0,
        history=[],
        model="v72_dual_sleeve",
        use_model=True,
        portfolio_state_verified=True,
        lse_adapter=None,
    )

    assert out["ok"] is True
    assert out["blended_confidence"] <= 0.75 + 1e-9
    assert out["model"]["confidence"] <= 0.75 + 1e-9
    # Execution readiness/sizing must never surface the unclamped 0.9 either.
    assert out["confidence"].get("calibrated_probability") in (None,) or out["confidence"]["calibrated_probability"] <= 0.75 + 1e-9
    assert out["ticket"]["confidence_size_limit"] <= 1.0
