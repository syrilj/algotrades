import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import gamma_exposure  # noqa: E402


def test_flip_is_sign_crossing_near_spot_not_abs_min():
    # cum = [1, 3, -1, 0.5]: crossings at 27.5 (between 20/30) and 36.67 (between 30/40).
    # Old buggy code (cum.abs().idxmin()) returns 40. Correct near spot=31 is 27.5.
    net = pd.Series([1.0, 2.0, -4.0, 1.5], index=[10.0, 20.0, 30.0, 40.0])
    flip = gamma_exposure._zero_gamma_flip(net, spot=31.0)
    assert flip is not None
    assert abs(flip - 27.5) < 1e-9


def test_flip_picks_crossing_nearest_spot():
    net = pd.Series([1.0, 2.0, -4.0, 1.5], index=[10.0, 20.0, 30.0, 40.0])
    flip = gamma_exposure._zero_gamma_flip(net, spot=35.0)
    assert abs(flip - (30.0 + 10.0 * (1.0 / 1.5))) < 1e-9  # ≈36.667


def test_no_crossing_returns_none():
    net = pd.Series([1.0, 1.0, 1.0], index=[10.0, 20.0, 30.0])
    assert gamma_exposure._zero_gamma_flip(net, spot=20.0) is None


def test_leading_zero_run_is_not_a_false_crossing():
    # cum = [0, 0, 5, 7, 9, 12]: never goes negative -- no real crossing.
    # Buggy code flagged any exact-zero cumulative value as an automatic
    # "crossing" even with no sign change, returning strike=10.0 (WRONG).
    net = pd.Series(
        [0.0, 0.0, 5.0, 2.0, 2.0, 3.0],
        index=[10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
    )
    assert gamma_exposure._zero_gamma_flip(net, spot=15.0) is None


def test_interior_zero_touch_same_sign_is_not_a_crossing():
    # cum = [5, 0, 5]: touches zero at strike 20 but returns to the SAME
    # sign on both sides -- not a genuine flip.
    net = pd.Series([5.0, -5.0, 5.0], index=[10.0, 20.0, 30.0])
    assert gamma_exposure._zero_gamma_flip(net, spot=20.0) is None
