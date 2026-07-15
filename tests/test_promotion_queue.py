"""Tests for the promotion queue backend + winner decay check (Task 12).

SAFETY FOCUS: WINNER.json may only ever change inside approve(), and approve()
must never be self-invoked by nominate / winner_health / the compare_to_winners
wiring. These tests pin that contract down.

QUEUE_PATH is monkeypatched to tmp_path so no test ever touches the real
models/_shared/promotion_queue.json.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from evolve import promotion_queue as pq  # noqa: E402


CID = "mut_v23_devin_overlay_opts_dte_14"


def _seed_queue_path(monkeypatch, tmp_path):
    qpath = tmp_path / "promotion_queue.json"
    monkeypatch.setattr(pq, "QUEUE_PATH", qpath)
    return qpath


def _candidate(cid: str = CID):
    return {
        "id": cid,
        "campaign": "evolve_2026_07",
        "family": "poc_va_macdha",
        "model_dir": "/tmp/nonexistent/mut_model",
        "metrics": {"utility": 1.23, "sharpe": 2.1, "ret": 0.9, "dd": -0.11, "n": 55},
        "gates": {"claim_level": "CLAIM", "passed": True},
    }


# --- nominate --------------------------------------------------------------

def test_nominate_creates_pending_entry(monkeypatch, tmp_path):
    qpath = _seed_queue_path(monkeypatch, tmp_path)
    entry = pq.nominate(_candidate())
    assert entry["status"] == "pending"
    assert entry["id"] == CID
    assert qpath.exists()
    q = pq._load_queue()
    assert len(q) == 1
    assert q[0]["id"] == CID
    assert q[0]["status"] == "pending"


def test_nominate_dedupes_by_id(monkeypatch, tmp_path):
    _seed_queue_path(monkeypatch, tmp_path)
    pq.nominate(_candidate())
    pq.nominate(_candidate())  # same id -> must NOT create a second entry
    q = pq._load_queue()
    assert len(q) == 1


def test_nominate_never_promotes(monkeypatch, tmp_path):
    """nominate must never call approve, promote_mutation_to_models, or the
    WINNER-update helper."""
    _seed_queue_path(monkeypatch, tmp_path)

    def _boom(*a, **k):  # pragma: no cover - only fires on regression
        raise AssertionError("nominate must never promote / approve")

    from evolve import mutations

    monkeypatch.setattr(pq, "approve", _boom)
    monkeypatch.setattr(pq, "_update_winner", _boom)
    monkeypatch.setattr(mutations, "promote_mutation_to_models", _boom)

    pq.nominate(_candidate())  # must not raise
    assert pq._load_queue()[0]["status"] == "pending"


# --- reject ----------------------------------------------------------------

def test_reject_records_status(monkeypatch, tmp_path):
    _seed_queue_path(monkeypatch, tmp_path)
    pq.nominate(_candidate())
    out = pq.reject(CID, reason="dd too high")
    assert out["status"] == "rejected"
    assert out["reject_reason"] == "dd too high"
    q = pq._load_queue()
    assert q[0]["status"] == "rejected"


def test_reject_unknown_id_raises(monkeypatch, tmp_path):
    _seed_queue_path(monkeypatch, tmp_path)
    with pytest.raises(KeyError):
        pq.reject("does_not_exist")


# --- approve (human-only path) --------------------------------------------

def test_approve_promotes_via_stub_and_marks_approved(monkeypatch, tmp_path):
    _seed_queue_path(monkeypatch, tmp_path)
    pq.nominate(_candidate())

    calls = {"promote": 0, "winner": 0}
    from evolve import mutations

    def fake_promote(mut, *, family="poc_va_macdha", version_name=None):
        calls["promote"] += 1
        assert mut["id"] == CID
        assert mut["model_dir"] == "/tmp/nonexistent/mut_model"
        return Path("/tmp/models/poc_va_macdha/v_evolve_stub")

    def fake_update_winner(family, version, entry):
        calls["winner"] += 1
        assert version == "v_evolve_stub"
        return Path("/tmp/WINNER.json")

    monkeypatch.setattr(mutations, "promote_mutation_to_models", fake_promote)
    monkeypatch.setattr(pq, "_update_winner", fake_update_winner)
    monkeypatch.setattr(pq, "_record_promotion_finding", lambda *a, **k: None)

    out = pq.approve(CID)

    assert calls["promote"] == 1
    assert calls["winner"] == 1
    assert out["status"] == "approved"
    assert out["promoted_version"] == "v_evolve_stub"
    q = pq._load_queue()
    assert q[0]["status"] == "approved"


# --- winner_health (read-only decay check) ---------------------------------

def test_winner_health_degraded_below_threshold(monkeypatch, tmp_path):
    _seed_queue_path(monkeypatch, tmp_path)
    fake_stats = {"overall": {"n": 15, "live_wr": 0.25}, "rows": [], "asof": "x"}
    monkeypatch.setattr(pq.paper_ledger, "compute_stats", lambda **k: fake_stats)

    out = pq.winner_health(trailing_n=10)
    assert out["degraded"] is True
    assert out["live_wr"] == 0.25
    assert out["live_n"] == 15
    # PASS_BAR.json has no win-rate floor (win_rate is vanity_not_sufficient),
    # so the documented 0.40 fallback is used.
    assert out["threshold"] == pq._winrate_floor()
    assert out["threshold"] == 0.40


def test_winner_health_healthy_above_threshold(monkeypatch, tmp_path):
    _seed_queue_path(monkeypatch, tmp_path)
    fake_stats = {"overall": {"n": 20, "live_wr": 0.70}, "rows": [], "asof": "x"}
    monkeypatch.setattr(pq.paper_ledger, "compute_stats", lambda **k: fake_stats)

    out = pq.winner_health()
    assert out["degraded"] is False
    assert out["live_wr"] == 0.70


def test_winner_health_never_writes(monkeypatch, tmp_path):
    """winner_health is strictly read-only: no queue write, no WINNER write."""
    qpath = _seed_queue_path(monkeypatch, tmp_path)
    monkeypatch.setattr(
        pq.paper_ledger,
        "compute_stats",
        lambda **k: {"overall": {"n": 5, "live_wr": 0.3}, "asof": "x"},
    )

    def _boom(*a, **k):  # pragma: no cover - only fires on regression
        raise AssertionError("winner_health must be read-only")

    monkeypatch.setattr(pq, "_write_queue", _boom)
    monkeypatch.setattr(pq, "approve", _boom)
    monkeypatch.setattr(pq, "_update_winner", _boom)

    pq.winner_health()
    assert not qpath.exists()  # nothing written


# --- compare_to_winners wiring --------------------------------------------

def _promote_state():
    """A ranking state that reaches action == candidate_for_manual_promote."""
    return {
        "track": "equity",
        "ranking": [
            {
                "id": "mut_candidate_new_x",
                "utility": 5.0,  # well above frozen proxy * 0.5
                "claim_level": "CLAIM",
                "may_auto_promote": True,
            }
        ],
    }


def test_compare_to_winners_nominates_but_never_approves(monkeypatch, tmp_path):
    _seed_queue_path(monkeypatch, tmp_path)

    def _boom_approve(*a, **k):  # pragma: no cover - only fires on regression
        raise AssertionError("compare_to_winners wiring must never call approve()")

    monkeypatch.setattr(pq, "approve", _boom_approve)

    from evolve.finalize import compare_to_winners

    decision = compare_to_winners(_promote_state())

    assert decision["action"] == "candidate_for_manual_promote"
    q = pq._load_queue()
    assert len(q) == 1
    assert q[0]["id"] == "mut_candidate_new_x"
    assert q[0]["status"] == "pending"


def test_compare_to_winners_queue_error_does_not_crash_finalize(monkeypatch, tmp_path):
    _seed_queue_path(monkeypatch, tmp_path)

    def _explode(*a, **k):
        raise RuntimeError("simulated queue write failure")

    monkeypatch.setattr(pq, "nominate", _explode)

    from evolve.finalize import compare_to_winners

    # Must still return the decision, not raise.
    decision = compare_to_winners(_promote_state())
    assert decision["action"] == "candidate_for_manual_promote"
