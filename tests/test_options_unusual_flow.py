"""Unit tests for unusual options flow scoring (chain aggregate proxy)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import options_unusual_flow as ouf  # noqa: E402


def test_high_vol_oi_otm_short_dte_call_is_flagged():
    row = ouf.score_contract_row(
        symbol="TSLA",
        expiry="2026-07-18",
        dte=3,
        right="C",
        strike=280.0,
        spot=250.0,
        volume=5000,
        open_interest=400,
        mid=1.25,
    )
    assert row is not None
    assert row["unusual"] is True
    assert row["right"] == "C"
    assert row["strike"] == 280.0
    assert any("vol_vs_oi" in r for r in row["reasons"])
    assert row["score"] >= 28


def test_quiet_atm_is_not_flagged():
    row = ouf.score_contract_row(
        symbol="TSLA",
        expiry="2026-08-15",
        dte=30,
        right="C",
        strike=250.0,
        spot=250.0,
        volume=80,
        open_interest=5000,
        mid=8.0,
    )
    assert row is None


def test_large_premium_put_is_flagged_with_reason():
    row = ouf.score_contract_row(
        symbol="SPY",
        expiry="2026-07-25",
        dte=10,
        right="P",
        strike=580.0,
        spot=620.0,
        volume=2000,
        open_interest=1500,
        mid=2.5,  # premium = 2.5 * 2000 * 100 = 500k
    )
    assert row is not None
    assert row["right"] == "P"
    assert any("premium" in r for r in row["reasons"])
    assert "reason" in row and row["reason"]


def test_flag_unusual_from_frames_ranks_and_separates_quiet():
    spot = 100.0
    calls = pd.DataFrame(
        {
            "strike": [100.0, 110.0],
            "volume": [50.0, 3000.0],
            "openInterest": [8000.0, 200.0],
            "bid": [5.0, 0.4],
            "ask": [5.2, 0.5],
            "lastPrice": [5.1, 0.45],
            "impliedVolatility": [0.3, 0.55],
        }
    )
    puts = pd.DataFrame(
        {
            "strike": [100.0, 90.0],
            "volume": [40.0, 80.0],
            "openInterest": [7000.0, 4000.0],
            "bid": [4.8, 0.2],
            "ask": [5.0, 0.25],
            "lastPrice": [4.9, 0.22],
            "impliedVolatility": [0.28, 0.4],
        }
    )
    out = ouf.flag_unusual_from_frames(
        "TEST",
        spot,
        [("2026-07-18", 3, calls, puts)],
        top_n=10,
    )
    assert out["ok"] is True
    assert out["n_scanned"] == 4
    # Quiet ATM call/put should not dominate; OTM high vol/OI call should flag.
    flagged_strikes = {f["strike"] for f in out["flags"]}
    assert 110.0 in flagged_strikes
    assert 100.0 not in flagged_strikes or all(
        f["strike"] != 100.0 or f["score"] < out["flags"][0]["score"]
        for f in out["flags"]
    )
    for f in out["flags"]:
        assert f["unusual"] is True
        assert f.get("reason") or f.get("reasons")
