"""Per-symbol engine ranker confidence layer — anti-false-signal tests."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import symbol_ranker as sr  # noqa: E402


def _row(
    *,
    model: str = "v_test",
    n: int = 60,
    wr: float = 0.70,
    plr: float = 2.0,
    dd: float = -0.08,
    recent_ret: float = 0.10,
    oos: float = 1.0,
    score: float = 0.5,
    desk_runnable: bool = True,
    live: dict | None = None,
) -> dict:
    full = {
        "status": "ok",
        "trade_count": n,
        "win_rate": wr,
        "profit_loss_ratio": plr,
        "profit_factor": plr * wr / max(1e-9, 1 - wr),
        "max_drawdown": dd,
        "total_return": 0.2,
        "sharpe": 1.5,
    }
    recent = {"status": "ok", "trade_count": max(1, n // 3), "total_return": recent_ret}
    return {
        "model": model,
        "status": "ok",
        "desk_runnable": desk_runnable,
        "score": score,
        "oos_consistency": oos,
        "window_metrics": {"full": full, "recent": recent},
        "live": live,
    }


# --- wilson / breakeven math ---


def test_wilson_lower_bound_is_conservative_and_tightens_with_n():
    assert sr.wilson_lower_bound(0, 0) == 0.0
    lb_small = sr.wilson_lower_bound(0.7 * 10, 10)
    lb_big = sr.wilson_lower_bound(0.7 * 100, 100)
    assert lb_small < 0.7
    assert lb_big < 0.7
    assert lb_big > lb_small  # more evidence → tighter bound


def test_breakeven_win_rate():
    assert abs(sr.breakeven_win_rate(1.0) - 0.5) < 1e-9
    assert abs(sr.breakeven_win_rate(2.0) - 1.0 / 3.0) < 1e-9
    # Clamped for degenerate payoff ratios.
    assert sr.breakeven_win_rate(0.0) == sr.breakeven_win_rate(0.1)


# --- row confidence gates ---


def test_strong_evidence_earns_high_confidence():
    res = sr.row_confidence(_row(n=60, wr=0.70, plr=2.0))
    assert res["confidence"] >= 0.70
    assert res["parts"]["edge"] == 1.0


def test_no_statistical_edge_zeroes_confidence():
    # 55% WR at PLR 1.2 on 40 trades: Wilson LB below breakeven → no read.
    res = sr.row_confidence(_row(n=40, wr=0.55, plr=1.2))
    assert res["confidence"] == 0.0
    assert "win_rate_lb_below_breakeven" in res["reasons"]


def test_thin_sample_is_capped_even_with_perfect_headline_stats():
    res = sr.row_confidence(_row(n=8, wr=0.95, plr=3.0))
    assert res["confidence"] <= sr.CONF_THIN_CAP
    assert "thin_sample_capped" in res["reasons"]


def test_drawdown_hard_gate():
    res = sr.row_confidence(_row(n=60, wr=0.70, plr=2.0, dd=-0.30))
    assert res["confidence"] == 0.0
    assert "drawdown_gate" in res["reasons"]


def test_recent_window_decay_penalizes():
    good = sr.row_confidence(_row(recent_ret=0.10))
    decayed = sr.row_confidence(_row(recent_ret=-0.05))
    assert decayed["confidence"] < good["confidence"]
    assert "recent_window_negative" in decayed["reasons"]


def test_live_underperformance_reduces_confidence():
    base = sr.row_confidence(_row())
    hit = sr.row_confidence(_row(live={"n": 10, "avg_R": -0.6}))
    assert hit["confidence"] < base["confidence"]
    assert "live_underperformance" in hit["reasons"]


def test_options_track_capped():
    res = sr.row_confidence(_row(n=80, wr=0.75, plr=2.5), options_track=True)
    assert res["confidence"] <= sr.OPTIONS_CONF_CAP
    assert "synthetic_options_pricing_capped" in res["reasons"]


def test_error_row_is_zero():
    res = sr.row_confidence({"status": "error", "window_metrics": {}})
    assert res["confidence"] == 0.0
    assert "no_valid_full_window" in res["reasons"]


# --- ranking order ---


def test_rank_sort_puts_confidence_above_raw_score():
    lucky = _row(model="v_lucky", n=8, wr=0.95, plr=3.0, score=2.0)
    proven = _row(model="v_proven", n=60, wr=0.70, plr=2.0, score=0.6)
    rows = [lucky, proven]
    sr._apply_confidence(rows)
    sr._rank_sort(rows)
    assert rows[0]["model"] == "v_proven"
    assert rows[0]["rank"] == 1


# --- symbol-level read ---


def _art(rows: list[dict], *, stale: bool = False) -> dict:
    sr._apply_confidence(rows)
    return {"symbol": "TSLA", "asof": "2026-07-16T00:00:00Z", "stale": stale, "rows": rows}


def test_read_trusts_proven_engine():
    read = sr.confidence_read(_art([_row(model="v_proven")]), horizon="swing")
    assert read["verdict"] == "TRUST"
    assert read["model"] == "v_proven"
    assert read["confidence"] >= read["thresholds"]["enter"]


def test_read_abstains_when_no_engine_has_edge():
    rows = [
        _row(model="v_a", n=40, wr=0.55, plr=1.2),
        _row(model="v_b", n=30, wr=0.52, plr=1.1),
    ]
    read = sr.confidence_read(_art(rows), horizon="swing")
    assert read["verdict"] == "STAND_ASIDE"
    assert read["reasons"]  # named reason, never a silent abstain


def test_read_never_trusts_thin_sample():
    read = sr.confidence_read(_art([_row(model="v_thin", n=8, wr=0.95, plr=3.0)]))
    assert read["verdict"] != "TRUST"


def test_read_stale_artifact_stands_aside():
    read = sr.confidence_read(_art([_row()], stale=True))
    assert read["verdict"] == "STAND_ASIDE"
    assert "ranker_stale_refresh_required" in read["reasons"]


def test_read_ignores_non_desk_runnable():
    read = sr.confidence_read(_art([_row(desk_runnable=False)]))
    assert read["verdict"] == "STAND_ASIDE"
    assert "no_desk_runnable_evidence" in read["reasons"]


def test_read_reports_runner_up_gap():
    rows = [_row(model="v_a"), _row(model="v_b", n=25, wr=0.68, plr=1.8)]
    read = sr.confidence_read(_art(rows))
    assert read["runner_up"] is not None
    assert read["gap"] is not None
    assert read["gap"] >= 0
