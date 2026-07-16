"""Unit tests for v73 non-identity blend (not pure v39b identity)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
BLEND = ROOT / "models" / "poc_va_macdha" / "v73_trump_beat" / "blend.py"


def _load():
    name = f"v73_blend_test_{id(BLEND)}"
    spec = importlib.util.spec_from_file_location(name, BLEND)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


b = _load()


def test_agree_boost_increases_size_only_when_both_long():
    idx = pd.date_range("2025-01-01", periods=5, freq="h")
    primary = pd.Series([0.0, 1.0, 1.0, 0.0, 0.8], index=idx)
    secondary = pd.Series([0.0, 0.0, 1.0, 1.0, 1.0], index=idx)
    out = b.agree_boost(primary, secondary, boost=1.2, max_scale=1.5)
    assert out.iloc[1] == pytest.approx(1.0)  # primary long, secondary flat → no boost
    assert out.iloc[2] == pytest.approx(1.2)  # both long
    assert out.iloc[3] == pytest.approx(0.0)  # primary flat
    assert out.iloc[4] == pytest.approx(0.8 * 1.2)


def test_risk_on_scale_larger_when_calm_than_elevated():
    idx = pd.date_range("2025-01-01", periods=4, freq="h")
    primary = pd.Series([1.0, 1.0, 1.0, 1.0], index=idx)
    risk = pd.Series([0.0, 0.2, 0.8, 1.0], index=idx)
    out = b.risk_on_scale(primary, risk, max_boost=0.25, max_scale=1.5)
    assert out.iloc[0] > out.iloc[2]
    assert out.iloc[0] == pytest.approx(1.25)
    assert out.iloc[3] == pytest.approx(1.0)


def test_union_calm_fills_primary_flat_with_secondary():
    idx = pd.date_range("2025-01-01", periods=4, freq="h")
    primary = pd.Series([0.0, 0.0, 1.0, 0.0], index=idx)
    secondary = pd.Series([1.0, 1.0, 1.0, 0.0], index=idx)
    # bar0 elevated (no fill), bar1 calm (fill)
    risk = pd.Series([0.9, 0.1, 0.1, 0.1], index=idx)
    out = b.union_calm(primary, secondary, risk, calm_threshold=0.35, secondary_scale=0.8)
    assert out.iloc[0] == pytest.approx(0.0)
    assert out.iloc[1] == pytest.approx(0.8)
    assert out.iloc[2] > 0.0  # both long calm → boosted max


def test_pick_leader_not_always_primary():
    idx = pd.date_range("2025-01-01", periods=80, freq="h")
    # secondary long early with rising prices, primary long late with flat prices
    close = pd.Series(100.0, index=idx)
    close.iloc[:40] = np.linspace(100, 120, 40)
    close.iloc[40:] = 120.0
    primary = pd.Series(0.0, index=idx)
    primary.iloc[40:] = 1.0
    secondary = pd.Series(0.0, index=idx)
    secondary.iloc[:40] = 1.0
    out = b.pick_leader(primary, secondary, close, lookback=30)
    # After secondary's winning streak, leader should tilt secondary while primary still flat
    # At least some bars must differ from pure primary
    assert not out.equals(primary)


def test_high_beta_guard_cuts_elevated_high_beta_more_than_core():
    idx = pd.date_range("2025-01-01", periods=3, freq="h")
    primary = pd.Series([1.0, 1.0, 1.0], index=idx)
    risk = pd.Series([0.0, 0.2, 0.8], index=idx)  # last bar elevated
    secondary = pd.Series([1.0, 1.0, 1.0], index=idx)
    hb = b.high_beta_guard(
        primary, risk, is_high_beta=True, secondary=secondary,
        boost=1.10, high_beta_base=0.90, high_beta_elevated=0.50,
        calm_threshold=0.4, elevated_threshold=0.5, position_cap=1.0,
    )
    core = b.high_beta_guard(
        primary, risk, is_high_beta=False, secondary=secondary,
        boost=1.10, core_elevated=0.90,
        calm_threshold=0.4, elevated_threshold=0.5, position_cap=1.0,
    )
    # elevated bar: high-beta cut harder than core
    assert float(hb.iloc[2]) < float(core.iloc[2])
    assert float(hb.iloc[2]) == pytest.approx(0.50)
    # non-identity: elevated high-beta != raw primary
    assert float(hb.iloc[2]) != float(primary.iloc[2])
    # high-beta base applies on calm bars (0.90 base * optional tiny agree)
    assert float(hb.iloc[0]) <= 1.05 + 1e-9
    assert float(hb.iloc[0]) < float(primary.iloc[0]) or float(hb.iloc[0]) != 1.0


def test_inv_vol_scale_shrinks_high_vol_relative_to_low_vol():
    idx = pd.date_range("2025-01-01", periods=120, freq="h")
    rng = np.random.default_rng(0)
    # high vol close
    hi = 100 * np.cumprod(1 + rng.normal(0, 0.03, size=120))
    lo = 100 * np.cumprod(1 + rng.normal(0, 0.003, size=120))
    primary = pd.Series(1.0, index=idx)
    out_hi = b.inv_vol_scale(primary, pd.Series(hi, index=idx), target_vol=0.01, position_cap=2.0)
    out_lo = b.inv_vol_scale(primary, pd.Series(lo, index=idx), target_vol=0.01, position_cap=2.0)
    assert float(out_hi.iloc[-20:].mean()) < float(out_lo.iloc[-20:].mean())


def test_name_dd_cut_reduces_size_after_peak_drop():
    idx = pd.date_range("2025-01-01", periods=50, freq="h")
    close = pd.Series(np.concatenate([np.linspace(100, 120, 30), np.linspace(120, 100, 20)]), index=idx)
    primary = pd.Series(1.0, index=idx)
    out = b.name_dd_cut(primary, close, soft=-0.03, hard=-0.15, min_mult=0.3, position_cap=1.0)
    assert float(out.iloc[-1]) < float(out.iloc[25])
    assert float(out.iloc[-1]) < 1.0


def test_multi_lock_blend_not_identity_and_caps():
    idx = pd.date_range("2025-01-01", periods=80, freq="h")
    rng = np.random.default_rng(1)
    close = pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.02, size=80)), index=idx)
    primary = pd.Series(0.9, index=idx)
    secondary = pd.Series(0.9, index=idx)
    risk = pd.Series(0.1, index=idx)
    out = b.multi_lock_blend(
        primary, close, secondary=secondary, risk_score=risk,
        boost=1.08, position_cap=0.40, use_inv_vol=True, use_name_dd=True,
    )
    assert float(out.max()) <= 0.40 + 1e-9
    # non-identity: not a constant 0.9 series
    assert not np.allclose(out.values, primary.values)


def test_blend_signals_dispatch_agree_risk_on_non_identity():
    idx = pd.date_range("2025-01-01", periods=3, freq="h")
    primary = pd.Series([1.0, 1.0, 0.0], index=idx)
    secondary = pd.Series([1.0, 0.0, 0.0], index=idx)
    risk = pd.Series([0.0, 0.0, 0.0], index=idx)
    out = b.blend_signals(
        "agree_risk_on",
        primary,
        secondary=secondary,
        risk_score=risk,
        params={"boost": 1.2, "max_boost": 0.2, "max_scale": 1.5},
    )
    # bar0: agree + risk-on calm → > 1.0
    assert float(out.iloc[0]) > 1.0
    # bar1: no agree, still risk-on scale on primary
    assert float(out.iloc[1]) >= 1.0
    assert float(out.iloc[2]) == 0.0
