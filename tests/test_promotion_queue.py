"""Tests for the promotion queue backend + winner decay check (Task 12).

SAFETY FOCUS: WINNER.json may only ever change inside approve(), and approve()
must never be self-invoked by nominate / winner_health / the compare_to_winners
wiring. These tests pin that contract down.

QUEUE_PATH is monkeypatched to tmp_path so no test ever touches the real
models/_shared/promotion_queue.json.
"""
import sys
import json
import shutil
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
        "data_contract": {"source": "local", "interval": "1H"},
    }


def _valid_candidate(tmp_path: Path, cid: str = CID):
    model_dir = tmp_path / "candidate_bundle"
    model_dir.mkdir()
    (model_dir / "signal_engine.py").write_text("class SignalEngine:\n    pass\n")
    (model_dir / "config.json").write_text('{"mode": "daily"}\n')
    evidence = model_dir / "results.json"
    evidence.write_text('{"sharpe": 2.1, "n": 55}\n')
    calibration = model_dir / "calibration.json"
    calibration.write_text(
        '{"method": "platt", "status": "passed", '
        '"probability_calibrated": true, "cross_fitted": true}\n'
    )
    candidate = _candidate(cid)
    candidate.update(
        {
            "model_dir": str(model_dir),
            "evidence": [str(evidence)],
            "calibration_artifact": str(calibration),
            "data_contract": {"source": "local", "interval": "1H"},
        }
    )
    return candidate


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
    candidate = _valid_candidate(tmp_path)
    pq.nominate(candidate)

    calls = {"promote": 0, "winner": 0}
    from evolve import mutations

    def fake_promote(mut, *, family="poc_va_macdha", version_name=None):
        calls["promote"] += 1
        assert mut["id"] == CID
        assert mut["model_dir"] == candidate["model_dir"]
        dest = tmp_path / "models" / "poc_va_macdha" / "v_evolve_stub"
        shutil.copytree(mut["model_dir"], dest)
        return dest

    def fake_update_control_plane(family, version, dest, entry):
        calls["winner"] += 1
        assert version == "v_evolve_stub"
        return Path("/tmp/DEPLOYMENT_MANIFEST.json"), Path("/tmp/WINNER.json")

    monkeypatch.setattr(mutations, "promote_mutation_to_models", fake_promote)
    monkeypatch.setattr(pq, "_update_deployment_control_plane", fake_update_control_plane)
    monkeypatch.setattr(pq, "_record_promotion_finding", lambda *a, **k: None)

    out = pq.approve(CID)

    assert calls["promote"] == 1
    assert calls["winner"] == 1
    assert out["status"] == "approved"
    assert out["promoted_version"] == "v_evolve_stub"
    q = pq._load_queue()
    assert q[0]["status"] == "approved"


def test_approve_requires_pending_passed_and_integrity(monkeypatch, tmp_path):
    _seed_queue_path(monkeypatch, tmp_path)
    pq.nominate(_candidate())
    with pytest.raises(ValueError, match="integrity snapshot"):
        pq.approve(CID)

    q = pq._load_queue()
    q[0]["status"] = "rejected"
    pq._write_queue(q)
    with pytest.raises(ValueError, match="only pending"):
        pq.approve(CID)


def test_approve_rejects_bundle_changed_after_nomination(monkeypatch, tmp_path):
    _seed_queue_path(monkeypatch, tmp_path)
    candidate = _valid_candidate(tmp_path)
    pq.nominate(candidate)
    (Path(candidate["model_dir"]) / "signal_engine.py").write_text("tampered = True\n")
    with pytest.raises(ValueError, match="bytes changed"):
        pq.approve(CID)


def test_approve_rejects_candidate_that_did_not_pass_gates(monkeypatch, tmp_path):
    _seed_queue_path(monkeypatch, tmp_path)
    candidate = _valid_candidate(tmp_path)
    candidate["gates"]["passed"] = False
    pq.nominate(candidate)
    with pytest.raises(ValueError, match="gates did not pass"):
        pq.approve(CID)


def test_approve_rejects_identity_or_uncrossfitted_calibration(monkeypatch, tmp_path):
    _seed_queue_path(monkeypatch, tmp_path)
    candidate = _valid_candidate(tmp_path)
    calibration = Path(candidate["calibration_artifact"])
    calibration.write_text(
        '{"status": "active", "probability_calibrated": false, '
        '"cross_fitted": false, "calibration_type": "identity"}\n'
    )
    pq.nominate(candidate)
    with pytest.raises(ValueError, match="cross-fitted probability calibrator"):
        pq.approve(CID)


def test_approve_atomically_updates_manifest_and_winner(monkeypatch, tmp_path):
    monkeypatch.setattr(pq, "ROOT", tmp_path)
    _seed_queue_path(monkeypatch, tmp_path)
    family_dir = tmp_path / "models" / "poc_va_macdha"
    family_dir.mkdir(parents=True)
    (family_dir / "DEPLOYMENT_MANIFEST.json").write_text(
        json.dumps({"schema_version": 1, "active": {"equity_model": "v72_dual_sleeve"}})
    )
    (family_dir / "WINNER.json").write_text(json.dumps({"winner": "v72_dual_sleeve"}))
    candidate = _valid_candidate(tmp_path, cid="candidate_atomic")
    pq.nominate(candidate)

    from evolve import mutations

    def fake_promote(mut, *, family="poc_va_macdha", version_name=None):
        dest = family_dir / "v_evolve_atomic"
        shutil.copytree(mut["model_dir"], dest)
        return dest

    monkeypatch.setattr(mutations, "promote_mutation_to_models", fake_promote)
    monkeypatch.setattr(pq, "_record_promotion_finding", lambda *a, **k: None)
    out = pq.approve("candidate_atomic")

    manifest = json.loads((family_dir / "DEPLOYMENT_MANIFEST.json").read_text())
    winner = json.loads((family_dir / "WINNER.json").read_text())
    assert manifest["active"]["equity_model"] == "v_evolve_atomic"
    assert manifest["rollback_model"] == "v72_dual_sleeve"
    assert manifest["promotion_evidence"][0]["sha256"]
    assert manifest["calibration"]["sha256"]
    assert winner["winner"] == "v_evolve_atomic"
    assert winner["previous_winner"] == "v72_dual_sleeve"
    assert out["status"] == "approved"


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
