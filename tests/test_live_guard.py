from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.confidence_shadow import ShadowDecisionLedger
from tools.live_guard import (
    DEFAULT_WINDOW,
    WR_BREACH_MARGIN,
    build_verdict,
    evaluate_breach,
    load_bootstrap_floor,
    load_holdout_bands,
    main,
    rolling_enter_stats,
)


HOLDOUT_WR = 0.6547619047619048  # locked v72 oos win rate (runs/v72_dual_sleeve/STATE.json)


# ---------------------------------------------------------------------------
# Fixtures: tmp copies of every evidence file so nothing real is ever touched.
# ---------------------------------------------------------------------------


@pytest.fixture()
def state_path(tmp_path: Path) -> Path:
    path = tmp_path / "STATE.json"
    path.write_text(
        json.dumps(
            {
                "results": {
                    "v72_dual_sleeve": {
                        "oos": {"wr": HOLDOUT_WR, "ret": 0.816, "dd": -0.196, "sharpe": 2.199, "n": 84}
                    }
                }
            }
        )
    )
    return path


@pytest.fixture()
def calibration_dir(tmp_path: Path) -> Path:
    cal_dir = tmp_path / "calibration"
    cal_dir.mkdir()
    (cal_dir / "v72_dual_sleeve.json").write_text(
        json.dumps({"action_band": {"bootstrap_p05_mean_realized_r": 0.0324, "enter": 0.625, "n": 98}})
    )
    return cal_dir


@pytest.fixture()
def manifest_path(tmp_path: Path) -> Path:
    path = tmp_path / "DEPLOYMENT_MANIFEST.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "family": "poc_va_macdha",
                "updated_at": "2026-07-16T00:00:00Z",
                "updated_by": "control-plane-reconciliation",
                "active": {
                    "equity_model": "v72_dual_sleeve",
                    "bundle": {"path": "models/poc_va_macdha/v72_dual_sleeve", "signal_engine_sha256": "abc"},
                },
                "fallbacks": {"equity": ["v39d_confluence", "v71_live_confidence"], "policy": "ordered_fail_closed"},
                "rollback_model": "v39d_confluence",
                "execution_readiness": {
                    "model_routing": "ready",
                    "probability_sized_execution": "blocked_until_cross_fitted_calibrator_passes",
                },
                "data_contract": {"interval": "1H"},
            },
            indent=2,
        )
    )
    return path


def _ledger_with_rows(tmp_path: Path, rows: list[dict], raw_lines: list[str] | None = None) -> ShadowDecisionLedger:
    ledger_path = tmp_path / "shadow_decisions.jsonl"
    lines = [json.dumps(row, sort_keys=True) for row in rows]
    if raw_lines:
        lines.extend(raw_lines)
    ledger_path.write_text("\n".join(lines) + "\n")
    return ShadowDecisionLedger(ledger_path)


def _enter_row(i: int, outcome: float, realized: float, model: str = "v72_dual_sleeve") -> dict:
    return {
        "event_id": f"evt{i:04d}",
        "model": model,
        "state": "ENTER",
        "outcome": outcome,
        "realized_return": realized,
        "settled_at_utc": f"2026-07-{(i % 28) + 1:02d}T00:00:00+00:00",
        "recorded_at_utc": f"2026-07-{(i % 28) + 1:02d}T00:00:00+00:00",
    }


def _healthy_rows(n: int = 25) -> list[dict]:
    # WR 0.72, mean R positive — inside the holdout band.
    rows = []
    for i in range(n):
        won = (i % 25) < 18
        rows.append(_enter_row(i, 1.0 if won else 0.0, 0.04 if won else -0.02))
    return rows


def _breaching_rows(n: int = 25) -> list[dict]:
    # WR 0.2 — far below holdout 0.6548 - 0.15 margin = 0.5048.
    rows = []
    for i in range(n):
        won = (i % 5) == 0
        rows.append(_enter_row(i, 1.0 if won else 0.0, 0.03 if won else -0.03))
    return rows


# ---------------------------------------------------------------------------
# Rolling statistics.
# ---------------------------------------------------------------------------


def test_rolling_stats_computes_wr_and_mean_r_over_window():
    rows = _healthy_rows(40)
    stats = rolling_enter_stats(rows, window=20, model="v72_dual_sleeve")
    assert stats["n"] == 20
    assert stats["n_total_settled_enter"] == 40
    assert 0.0 <= stats["win_rate"] <= 1.0
    assert stats["mean_realized_return"] is not None


def test_rolling_stats_skips_watch_and_unsettled_rows():
    rows = _healthy_rows(5)
    rows.append({"state": "WATCH", "outcome": 1.0, "realized_return": 0.05, "model": "v72_dual_sleeve"})
    rows.append({"state": "ENTER", "outcome": None, "realized_return": None, "model": "v72_dual_sleeve"})
    stats = rolling_enter_stats(rows, window=20, model="v72_dual_sleeve")
    assert stats["n"] == 5


def test_rolling_stats_skips_corrupt_rows():
    rows = _healthy_rows(5)
    rows.append({"state": "ENTER", "outcome": "corrupt", "realized_return": 0.05, "model": "v72_dual_sleeve"})
    rows.append({"state": "ENTER", "outcome": 1.0, "realized_return": float("nan"), "model": "v72_dual_sleeve"})
    rows.append("not-a-dict")  # type: ignore[list-item]
    stats = rolling_enter_stats(rows, window=20, model="v72_dual_sleeve")
    assert stats["n"] == 5


def test_rolling_stats_filters_by_model():
    rows = _healthy_rows(5) + [_enter_row(99, 0.0, -0.5, model="v39d_confluence")]
    stats = rolling_enter_stats(rows, window=20, model="v72_dual_sleeve")
    assert stats["n"] == 5


# ---------------------------------------------------------------------------
# Evidence loaders fail closed.
# ---------------------------------------------------------------------------


def test_load_holdout_bands_missing_file_fails_closed(tmp_path):
    out = load_holdout_bands(tmp_path / "missing.json")
    assert out["available"] is False


def test_load_bootstrap_floor_missing_file_fails_closed(tmp_path):
    out = load_bootstrap_floor(tmp_path, model="v72_dual_sleeve")
    assert out["available"] is False


def test_load_holdout_bands_reads_fixture(state_path):
    out = load_holdout_bands(state_path)
    assert out["available"] is True
    assert out["win_rate"] == pytest.approx(HOLDOUT_WR)


# ---------------------------------------------------------------------------
# Breach evaluation.
# ---------------------------------------------------------------------------


def test_insufficient_data_never_breaches():
    rolling = {"n": 3, "win_rate": 0.0, "mean_realized_return": -0.5, "window": 20}
    out = evaluate_breach(rolling, {"available": True, "win_rate": HOLDOUT_WR}, {"available": True, "bootstrap_p05_mean_realized_r": 0.03}, window=20)
    assert out["breach"] is False
    assert out["status"] == "insufficient_data"


def test_missing_all_evidence_reports_unavailable_not_ok():
    rolling = {"n": 20, "win_rate": 0.7, "mean_realized_return": 0.05, "window": 20}
    out = evaluate_breach(rolling, {"available": False, "reason": "x"}, {"available": False, "reason": "y"}, window=20)
    assert out["breach"] is False
    assert out["status"] == "evidence_unavailable"


def test_wr_below_floor_triggers_breach():
    rolling = {"n": 20, "win_rate": 0.20, "mean_realized_return": 0.01, "window": 20}
    out = evaluate_breach(rolling, {"available": True, "win_rate": HOLDOUT_WR}, {"available": False, "reason": "y"}, window=20)
    assert out["breach"] is True
    assert out["status"] == "DEMOTE"
    assert any("win_rate_breach" in r for r in out["trigger_reasons"])


def test_wr_within_margin_does_not_breach():
    rolling = {"n": 20, "win_rate": HOLDOUT_WR - WR_BREACH_MARGIN + 0.01, "mean_realized_return": 0.02, "window": 20}
    out = evaluate_breach(rolling, {"available": True, "win_rate": HOLDOUT_WR}, {"available": True, "bootstrap_p05_mean_realized_r": 0.03}, window=20)
    assert out["breach"] is False
    assert out["status"] == "OK"


def test_negative_mean_r_with_negative_p05_triggers_breach():
    rolling = {"n": 20, "win_rate": 0.60, "mean_realized_return": -0.02, "window": 20}
    out = evaluate_breach(
        rolling,
        {"available": True, "win_rate": 0.60},  # WR leg healthy
        {"available": True, "bootstrap_p05_mean_realized_r": -0.01},
        window=20,
    )
    assert out["breach"] is True
    assert any("mean_r_breach" in r for r in out["trigger_reasons"])


def test_negative_mean_r_with_positive_p05_does_not_breach_mean_r_leg():
    # Pre-registered p05 floor is positive (as in the real v72 artifact):
    # the mean-R leg alone must not demote on a merely-negative rolling mean.
    rolling = {"n": 20, "win_rate": 0.60, "mean_realized_return": -0.02, "window": 20}
    out = evaluate_breach(
        rolling,
        {"available": True, "win_rate": 0.60},
        {"available": True, "bootstrap_p05_mean_realized_r": 0.0324},
        window=20,
    )
    assert out["breach"] is False


# ---------------------------------------------------------------------------
# End-to-end verdicts against tmp fixtures.
# ---------------------------------------------------------------------------


def test_healthy_ledger_produces_no_demotion(tmp_path, state_path, calibration_dir, manifest_path):
    ledger = _ledger_with_rows(tmp_path, _healthy_rows(25))
    verdict = build_verdict(
        ledger=ledger,
        state_path=state_path,
        calibration_dir=calibration_dir,
        manifest_path=manifest_path,
    )
    assert verdict["breach"] is False
    assert verdict["status"] == "OK"
    assert verdict["rollback_model"] == "v39d_confluence"


def test_breaching_ledger_produces_demote_verdict(tmp_path, state_path, calibration_dir, manifest_path):
    ledger = _ledger_with_rows(tmp_path, _breaching_rows(25))
    verdict = build_verdict(
        ledger=ledger,
        state_path=state_path,
        calibration_dir=calibration_dir,
        manifest_path=manifest_path,
    )
    assert verdict["breach"] is True
    assert verdict["status"] == "DEMOTE"
    assert verdict["rollback_model"] == "v39d_confluence"
    assert verdict["trigger_reasons"]


def test_corrupt_ledger_lines_are_skipped_not_fatal(tmp_path, state_path, calibration_dir, manifest_path):
    ledger = _ledger_with_rows(
        tmp_path,
        _healthy_rows(25),
        raw_lines=["{not valid json", '{"state": "ENTER", "outcome": "??", "model": "v72_dual_sleeve"}'],
    )
    verdict = build_verdict(
        ledger=ledger,
        state_path=state_path,
        calibration_dir=calibration_dir,
        manifest_path=manifest_path,
    )
    assert verdict["breach"] is False
    assert verdict["rolling"]["n"] == 20


# ---------------------------------------------------------------------------
# CLI: dry-run never mutates; --apply flips the tmp manifest copy.
# ---------------------------------------------------------------------------


def _cli_args(tmp_path, ledger, state_path, calibration_dir, manifest_path, verdict_path, apply=False):
    args = [
        "--ledger-path", str(ledger.path),
        "--state-path", str(state_path),
        "--calibration-dir", str(calibration_dir),
        "--manifest-path", str(manifest_path),
        "--verdict-path", str(verdict_path),
    ]
    if apply:
        args.append("--apply")
    return args


def test_dry_run_default_never_mutates_manifest(tmp_path, state_path, calibration_dir, manifest_path):
    ledger = _ledger_with_rows(tmp_path, _breaching_rows(25))
    verdict_path = tmp_path / "live_guard_STATE.json"
    before = manifest_path.read_text()

    rc = main(_cli_args(tmp_path, ledger, state_path, calibration_dir, manifest_path, verdict_path))

    assert rc == 1  # breach detected
    assert manifest_path.read_text() == before  # manifest untouched
    verdict = json.loads(verdict_path.read_text())
    assert verdict["status"] == "DEMOTE"
    assert verdict["dry_run"] is True
    assert verdict["mutation_applied"] is False


def test_apply_flips_manifest_to_rollback_on_breach(tmp_path, state_path, calibration_dir, manifest_path):
    ledger = _ledger_with_rows(tmp_path, _breaching_rows(25))
    verdict_path = tmp_path / "live_guard_STATE.json"

    rc = main(_cli_args(tmp_path, ledger, state_path, calibration_dir, manifest_path, verdict_path, apply=True))

    assert rc == 1
    manifest = json.loads(manifest_path.read_text())
    assert manifest["active"]["equity_model"] == "v39d_confluence"
    assert manifest["execution_readiness"]["model_routing"] == "blocked_by_live_guard"
    # Everything else preserved verbatim.
    assert manifest["rollback_model"] == "v39d_confluence"
    assert manifest["active"]["bundle"]["signal_engine_sha256"] == "abc"
    assert manifest["fallbacks"]["equity"] == ["v39d_confluence", "v71_live_confidence"]
    assert manifest["execution_readiness"]["probability_sized_execution"] == "blocked_until_cross_fitted_calibrator_passes"
    assert manifest["updated_by"] == "live_guard"
    assert manifest["updated_at"] != "2026-07-16T00:00:00Z"
    assert manifest["live_guard_history"][0]["to_equity_model"] == "v39d_confluence"

    verdict = json.loads(verdict_path.read_text())
    assert verdict["mutation_applied"] is True


def test_apply_with_healthy_ledger_never_mutates(tmp_path, state_path, calibration_dir, manifest_path):
    ledger = _ledger_with_rows(tmp_path, _healthy_rows(25))
    verdict_path = tmp_path / "live_guard_STATE.json"
    before = manifest_path.read_text()

    rc = main(_cli_args(tmp_path, ledger, state_path, calibration_dir, manifest_path, verdict_path, apply=True))

    assert rc == 0
    assert manifest_path.read_text() == before


def test_default_window_constant():
    assert DEFAULT_WINDOW == 20
