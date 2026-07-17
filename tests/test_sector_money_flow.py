"""Deterministic tests for sector money-flow scanner (no network)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tools.sector_money_flow import (
    DEFINITIVE_SCORE_CUT,
    build_report,
    classify_direction,
    classify_rotation,
    definitive_assessment,
    flow_score,
    ret_n,
    rs_n,
    score_sectors,
    trading_notes,
)


def _series(start: float, rets: list[float], idx: pd.DatetimeIndex | None = None) -> pd.Series:
    vals = [start]
    for r in rets:
        vals.append(vals[-1] * (1.0 + r))
    if idx is None:
        idx = pd.date_range("2025-01-01", periods=len(vals), freq="B")
    return pd.Series(vals, index=idx[: len(vals)], dtype=float)


def _ohlcv_from_close(close: pd.Series, volume: float | pd.Series = 1_000_000.0) -> pd.DataFrame:
    c = close.astype(float)
    if isinstance(volume, (int, float)):
        vol = pd.Series(float(volume), index=c.index)
    else:
        vol = volume.reindex(c.index).ffill()
    return pd.DataFrame(
        {
            "open": c,
            "high": c * 1.001,
            "low": c * 0.999,
            "close": c,
            "volume": vol.astype(float),
        },
        index=c.index,
    )


def test_ret_n_and_rs_n():
    idx = pd.date_range("2025-01-01", periods=30, freq="B")
    # flat then +10% last day
    spy = pd.Series(100.0, index=idx)
    sec = spy.copy()
    sec.iloc[-1] = 110.0
    assert ret_n(sec, 1) == pytest.approx(0.10, abs=1e-9)
    assert rs_n(sec, spy, 1) == pytest.approx(0.10, abs=1e-9)


def test_definitive_requires_horizon_agreement():
    # All horizons agree + material RS + volume → definitive
    score, flag, reasons = definitive_assessment(
        rs_1d=0.01,
        rs_5d=0.02,
        rs_21d=0.015,
        ret_1d=0.008,
        ret_5d=0.025,
        above=True,
        rvol=1.5,
        direction="in",
    )
    assert score >= DEFINITIVE_SCORE_CUT
    assert flag is True
    assert any("agree" in r for r in reasons)

    # Horizons disagree → not definitive
    score2, flag2, _ = definitive_assessment(
        rs_1d=0.01,
        rs_5d=-0.01,
        rs_21d=0.01,
        ret_1d=0.002,
        ret_5d=-0.005,
        above=None,
        rvol=1.0,
        direction="in",
    )
    assert flag2 is False
    assert score2 < DEFINITIVE_SCORE_CUT


def test_score_sectors_money_in_and_out():
    """Tech rips vs SPY; staples lag — money in XLK, out XLP."""
    n = 60
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    rng = np.random.default_rng(42)
    # SPY mild drift
    spy_rets = rng.normal(0.0002, 0.004, size=n - 1)
    spy = _series(100.0, list(spy_rets), idx)

    # XLK strongly outperforms last 21d + last day
    xlk_rets = list(spy_rets)
    for i in range(-21, 0):
        xlk_rets[i] = spy_rets[i] + 0.004
    xlk_rets[-1] = spy_rets[-1] + 0.01
    xlk = _series(100.0, xlk_rets, idx)

    # XLP underperforms
    xlp_rets = list(spy_rets)
    for i in range(-21, 0):
        xlp_rets[i] = spy_rets[i] - 0.003
    xlp_rets[-1] = spy_rets[-1] - 0.008
    xlp = _series(100.0, xlp_rets, idx)

    # Volume spike on XLK last bar
    xlk_vol = pd.Series(1_000_000.0, index=idx)
    xlk_vol.iloc[-1] = 2_000_000.0

    panel = {
        "SPY": _ohlcv_from_close(spy),
        "XLK": _ohlcv_from_close(xlk, xlk_vol),
        "XLP": _ohlcv_from_close(xlp),
        "XLY": _ohlcv_from_close(xlk * 0.99),  # also risk-on-ish
        "XLV": _ohlcv_from_close(xlp * 1.01),
    }
    meta = {
        "XLK": {"name": "Tech", "bucket": "tech", "names": ["NVDA"]},
        "XLP": {"name": "Staples", "bucket": "defensive", "names": ["PG"]},
        "XLY": {"name": "Discretionary", "bucket": "growth", "names": ["AMZN"]},
        "XLV": {"name": "Health", "bucket": "defensive", "names": ["JNJ"]},
    }
    rows = score_sectors(panel, sector_meta=meta)
    by = {r.etf: r for r in rows}
    assert by["XLK"].flow_direction == "in"
    assert by["XLP"].flow_direction == "out"
    assert by["XLK"].flow_score > by["XLP"].flow_score


def test_semis_to_tech_day_rotation():
    """SOXX dumps today while XLK bids — named semis→tech rotation."""
    from tools.sector_money_flow import detect_theme_rotations, market_context

    n = 40
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    spy = _series(100.0, [0.0005] * (n - 1), idx)
    # SOXX flat then hard down last day
    soxx_rets = [0.0005] * (n - 2) + [-0.025]
    soxx = _series(100.0, soxx_rets, idx)
    # XLK flat then up last day
    xlk_rets = [0.0005] * (n - 2) + [0.012]
    xlk = _series(100.0, xlk_rets, idx)
    igv = _series(100.0, [0.0005] * (n - 2) + [0.010], idx)

    panel = {
        "SPY": _ohlcv_from_close(spy),
        "SOXX": _ohlcv_from_close(soxx),
        "XLK": _ohlcv_from_close(xlk),
        "IGV": _ohlcv_from_close(igv),
        "XLP": _ohlcv_from_close(spy * 0.999),
    }
    meta = {
        "SOXX": {"name": "Semis", "bucket": "semis", "theme": True, "names": ["NVDA"]},
        "XLK": {"name": "Tech", "bucket": "tech", "theme": False, "names": ["MSFT"]},
        "IGV": {"name": "Software", "bucket": "software", "theme": True, "names": ["CRM"]},
        "XLP": {"name": "Staples", "bucket": "defensive", "theme": False, "names": ["PG"]},
    }
    rows = score_sectors(panel, sector_meta=meta)
    by = {r.etf: r for r in rows}
    assert by["SOXX"].flow_direction == "out"
    assert by["XLK"].flow_direction == "in"
    ctx = market_context(panel)
    rot = classify_rotation(rows, ctx)
    assert rot["kind"] == "semis_to_tech"
    themes = detect_theme_rotations(rows, ctx)
    assert any(t["id"] == "semis_to_tech" for t in themes)
    report = build_report(panel, source_used="synthetic", sector_meta=meta)
    assert report["ok"] is True
    assert report["rotation"]["kind"] == "semis_to_tech"


def test_build_report_contract_and_rotation_kind():
    n = 50
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    spy = _series(100.0, [0.001] * (n - 1), idx)
    # Growth leaders
    growth = _series(100.0, [0.003] * (n - 1), idx)
    # Defensive laggards
    defense = _series(100.0, [-0.001] * (n - 1), idx)

    panel = {
        "SPY": _ohlcv_from_close(spy),
        "QQQ": _ohlcv_from_close(growth),
        "XLK": _ohlcv_from_close(growth),
        "XLY": _ohlcv_from_close(growth),
        "XLP": _ohlcv_from_close(defense),
        "XLV": _ohlcv_from_close(defense),
        "XLU": _ohlcv_from_close(defense),
        "XLF": _ohlcv_from_close(spy),
        "XLE": _ohlcv_from_close(spy),
        "XLI": _ohlcv_from_close(spy),
        "XLB": _ohlcv_from_close(spy),
        "XLC": _ohlcv_from_close(growth * 0.998),
    }
    report = build_report(panel, source_used="synthetic")
    assert report["ok"] is True
    assert "rotation" in report
    assert "money_in" in report
    assert "money_out" in report
    assert "trading_notes" in report
    assert len(report["trading_notes"]) >= 4
    assert report["rotation"]["kind"] in {
        "risk_on",
        "internal",
        "broad_bid",
        "defensive",
        "unclear",
        "broad_risk_off",
        "semis_to_tech",
        "tech_to_semis",
    }
    # Growth should appear in money_in
    in_etfs = {r["etf"] for r in report["money_in"]}
    assert "XLK" in in_etfs or "XLY" in in_etfs


def test_defensive_rotation_notes():
    sectors = score_sectors(
        {
            "SPY": _ohlcv_from_close(_series(100.0, [0.0] * 40)),
            "XLP": _ohlcv_from_close(_series(100.0, [0.002] * 40)),
            "XLV": _ohlcv_from_close(_series(100.0, [0.002] * 40)),
            "XLK": _ohlcv_from_close(_series(100.0, [-0.002] * 40)),
            "XLY": _ohlcv_from_close(_series(100.0, [-0.002] * 40)),
        },
        sector_meta={
            "XLP": {"name": "Staples", "bucket": "defensive", "names": []},
            "XLV": {"name": "Health", "bucket": "defensive", "names": []},
            "XLK": {"name": "Tech", "bucket": "tech", "names": []},
            "XLY": {"name": "Disc", "bucket": "growth", "names": []},
        },
    )
    ctx = {
        "spy_ret_5d": 0.0,
        "spy_ret_1d": 0.0,
        "ratios": {
            "discretionary_vs_staples": {"ret_5d": -0.02},
            "tech_vs_staples": {"ret_5d": -0.02},
        },
    }
    rot = classify_rotation(sectors, ctx)
    notes = trading_notes(rot, sectors, ctx)
    assert any("Defensive" in n or "defensive" in n or "stand aside" in n.lower() for n in notes)


def test_classify_direction_neutral_band():
    assert classify_direction(0.0, rs_1d=0.0, rs_5d=0.0, day_mode=True) == "neutral"
    assert classify_direction(0.01, rs_1d=0.01, rs_5d=0.01, day_mode=True) == "in"
    assert classify_direction(-0.01, rs_1d=-0.01, rs_5d=-0.01, day_mode=True) == "out"


def test_flow_score_finite():
    s = flow_score(0.01, 0.02, 0.01, 0.005, True)
    assert np.isfinite(s)
    assert s > 0
