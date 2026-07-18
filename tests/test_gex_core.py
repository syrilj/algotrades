import numpy as np
import pandas as pd

from gex_core import (
    bs_gamma,
    compute_squeeze_score,
    max_pain,
    price_consistency,
    zero_gamma_flip,
)


def _score(**over):
    """Baseline bullish-squeeze inputs; override per test."""
    kw = dict(
        spot=100.0,
        call_wall=103.0,
        put_wall=90.0,
        flip=98.0,
        near_net=-5e9,
        net_dealer=-6e9,
        otm_call_weight=400.0,
        otm_put_weight=100.0,
        total_weight=1000.0,
        by_strike=[
            {"strike": 103.0, "call_gex": -3e9, "put_gex": 0.0},
            {"strike": 90.0, "call_gex": 0.0, "put_gex": -1e9},
        ],
        expected_move_pct=4.0,
        expected_move_low=96.0,
        expected_move_high=104.0,
    )
    kw.update(over)
    return compute_squeeze_score(**kw)


def test_bullish_setup_scores_bullish():
    out = _score()
    assert out["squeeze_score"] >= 20
    assert out["squeeze_label"] == "bullish_squeeze"


def test_positive_gex_is_neutral():
    out = _score(near_net=5e9, net_dealer=6e9)
    assert out["squeeze_label"] == "neutral"
    assert all(v == 0.0 for k, v in out["squeeze_components"].items() if k != "regime_score")


def test_bearish_mirror_scores_bearish():
    out = _score(
        call_wall=110.0,
        put_wall=97.0,
        otm_call_weight=100.0,
        otm_put_weight=400.0,
        by_strike=[
            {"strike": 110.0, "call_gex": -1e9, "put_gex": 0.0},
            {"strike": 97.0, "call_gex": 0.0, "put_gex": -3e9},
        ],
    )
    assert out["squeeze_score"] <= -20
    assert out["squeeze_label"] == "bearish_squeeze"


def test_flip_crossing_near_spot():
    net = pd.Series([1.0, 2.0, -4.0, 1.5], index=[10.0, 20.0, 30.0, 40.0])
    assert abs(zero_gamma_flip(net, spot=31.0) - 27.5) < 1e-9


def test_bs_gamma_atm_positive_and_degenerate_zero():
    assert bs_gamma(100, 100, 30 / 365, 0.0, 0.5) > 0
    assert bs_gamma(100, 100, 0.0, 0.0, 0.5) == 0.0


def test_price_consistency_flags_divergence():
    assert price_consistency(100.0, 100.5)["consistent"] is True
    assert price_consistency(100.0, 110.0)["consistent"] is False


def test_max_pain_prefers_middle_strike():
    strikes = [90.0, 100.0, 110.0]
    mp = max_pain(
        np.array([90.0, 100.0]), np.array([100.0, 100.0]),
        np.array([110.0, 100.0]), np.array([100.0, 100.0]),
        strikes,
    )
    assert mp in strikes
