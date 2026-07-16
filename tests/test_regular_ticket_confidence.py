"""Regular-ticket high-confidence routing for desk symbols the operator trades.

Drives real model_registry entry points (alias resolution, specialist map,
select_model_for_confidence, route_best_model) — not reimplemented fixtures.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import model_registry as mr  # noqa: E402

REGULAR_TICKETS = ("TSLA", "MU", "SKHY", "MSTR", "INFQ")
DESK_ROUTING = ROOT / "models" / "poc_va_macdha" / "DESK_ROUTING.json"


def test_desk_routing_alias_infq_to_ionq():
    routing = json.loads(DESK_ROUTING.read_text())
    alias = routing.get("alias") or {}
    assert alias.get("INFQ") == "IONQ" or alias.get("INFQ.US") == "IONQ.US"
    assert mr.resolve_desk_symbol("INFQ") == "IONQ.US"
    assert mr.resolve_desk_symbol("INFQ.US") == "IONQ.US"


def test_desk_specialists_for_named_regulars():
    """TSLA/MU/MSTR/IONQ have v65 specialists; SKHY does not."""
    tsla = mr.desk_specialist_for_symbol("TSLA")
    mu = mr.desk_specialist_for_symbol("MU")
    mstr = mr.desk_specialist_for_symbol("MSTR")
    ionq = mr.desk_specialist_for_symbol("IONQ")
    infq = mr.desk_specialist_for_symbol("INFQ")
    skhy = mr.desk_specialist_for_symbol("SKHY")

    assert tsla and tsla["model"] == "v65_spec_tsla"
    assert mu and mu["model"] == "v65_spec_mu"
    assert mstr and mstr["model"] == "v65_spec_mstr"
    assert ionq and ionq["model"] == "v65_spec_ionq"
    # INFQ must resolve through alias to the IONQ specialist path
    assert infq and infq["model"] == "v65_spec_ionq"
    assert infq["code"] == "IONQ.US"
    assert skhy is None


def test_high_wr_sleeve_is_v71_in_desk_routing():
    routing = mr.load_desk_routing()
    assert routing.get("high_wr_equity") == "v71_live_confidence"
    assert routing.get("dual_sleeve_equity") == "v72_dual_sleeve"
    assert routing.get("fallback_equity") == "v39d_confluence"
    assert (ROOT / "models" / "poc_va_macdha" / "v71_live_confidence" / "signal_engine.py").exists()


@pytest.mark.parametrize("symbol", REGULAR_TICKETS)
def test_day_confidence_prefers_high_wr_sleeve(symbol: str):
    """Day tickets: confidence ranker should surface v71 over dual-sleeve max-return."""
    hit = mr.select_model_for_confidence(symbol, horizon="day", desk_only=True, probe_fn=None)
    assert hit["source"] == "confidence_ranker"
    assert hit["horizon"] == "day"
    assert hit.get("model") == "v71_live_confidence", (
        f"{symbol} day expected v71_live_confidence, got {hit.get('model')} "
        f"score={hit.get('score')} reason={hit.get('reason')}"
    )
    assert float(hit.get("score") or 0) > 0.5
    models = [p.get("model") for p in (hit.get("probes") or [])]
    assert "v71_live_confidence" in models


@pytest.mark.parametrize(
    "symbol,expected_swing",
    [
        ("TSLA", "v65_spec_tsla"),
        ("MU", "v65_spec_mu"),
        ("MSTR", "v65_spec_mstr"),
        ("INFQ", "v65_spec_ionq"),
        ("IONQ", "v65_spec_ionq"),
    ],
)
def test_swing_confidence_prefers_desk_specialist(symbol: str, expected_swing: str):
    hit = mr.select_model_for_confidence(symbol, horizon="swing", desk_only=True, probe_fn=None)
    assert hit["source"] == "confidence_ranker"
    assert hit["horizon"] == "swing"
    assert hit.get("model") == expected_swing, (
        f"{symbol} swing expected {expected_swing}, got {hit.get('model')}"
    )
    if symbol == "INFQ":
        assert hit.get("code") == "IONQ.US"


def test_skhy_swing_falls_back_without_specialist():
    """SKHY has ranker artifact but no DESK specialist — swing uses standard track."""
    assert mr.desk_specialist_for_symbol("SKHY") is None
    hit = mr.select_model_for_confidence("SKHY", horizon="swing", desk_only=True, probe_fn=None)
    assert hit.get("model")
    # Must not invent a v65_spec_skhy
    assert not str(hit.get("model") or "").startswith("v65_spec_skhy")
    assert hit.get("track") in ("standard", "specialist", None) or hit.get("model")
    # Prefer known bag engines when no specialist
    assert hit["model"] in {
        "v39d_confluence",
        "v71_live_confidence",
        "v72_dual_sleeve",
        "v39b_live_adapt",
        "v50_high_win_rate",
        "v63_spy_prune",
        "v67_universal_specialist",
    }


def test_rank_models_for_symbol_surfaces_specialists():
    for sym, mid in (
        ("TSLA", "v65_spec_tsla"),
        ("MU", "v65_spec_mu"),
        ("MSTR", "v65_spec_mstr"),
        ("INFQ", "v65_spec_ionq"),
    ):
        ranks = mr.rank_models_for_symbol(sym)
        assert ranks, f"empty ranks for {sym}"
        top = ranks[0]
        assert top.get("model") == mid
        assert top.get("source") == "desk_specialist"


def test_confidence_sleeve_outranks_dual_sleeve_on_day_affinity():
    """Documented preference: for confidence goal, day affinity of v71 > v72."""
    aff_v71 = mr.model_horizon_affinity("v71_live_confidence", "day")
    aff_v72 = mr.model_horizon_affinity("v72_dual_sleeve", "day")
    assert aff_v71 >= aff_v72
    day = mr.route_best_model("TSLA", horizon="day")
    assert day.get("model") == "v71_live_confidence"
