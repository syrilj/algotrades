from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import pandas as pd
import numpy as np
import pytest

# Add repo root to python path to ensure imports work correctly
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import tools.dynamic_model_rank as dmr

PATH = ROOT / "models" / "poc_va_macdha" / "v83_adaptive_regime" / "signal_engine.py"


def test_v83_import():
    """Verify that the v83 SignalEngine can be imported successfully."""
    assert PATH.exists(), f"signal_engine.py not found at {PATH}"
    spec = importlib.util.spec_from_file_location("v83_test_engine", PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    assert hasattr(mod, "SignalEngine"), "SignalEngine not found in module"
    engine = mod.SignalEngine()
    assert engine is not None


class _SniperMock:
    def __init__(self, idx: pd.DatetimeIndex):
        self.idx = idx
        self.last_confidence = {"SPY.US": pd.Series([0.8, 0.8, 0.0], index=idx)}

    def generate(self, data_map):
        return {"SPY.US": pd.Series([0.225, 0.225, 0.0], index=self.idx)}


class _CoreMock:
    def __init__(self, idx: pd.DatetimeIndex):
        self.idx = idx

    def generate(self, data_map):
        return {"SPY.US": pd.Series([0.0, 0.30, 0.30], index=self.idx)}


def test_v83_generate_format_mocked():
    """Verify that the engine generates signals in the correct format with mocked sub-engines."""
    spec = importlib.util.spec_from_file_location("v83_test_engine", PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)

    # Instantiate and override with mock sub-engines to test vector merge logic
    engine = mod.SignalEngine.__new__(mod.SignalEngine)
    engine._sniper_name = "v71_live_confidence"
    engine._core_name = "v39d_confluence"
    engine._core_scale = 0.85
    engine._both_core_frac = 0.35
    engine._max_weight = 0.50
    engine._sniper_min_conf = 0.0
    engine.last_confidence = {}
    engine.last_sleeve = {}

    # Define mock regime scales to 1.0 so that core_regime_scale equals 1.0
    engine._core_trend_low_vol_scale = 1.0
    engine._core_trend_high_vol_scale = 1.0
    engine._core_chop_low_vol_scale = 1.0
    engine._core_chop_high_vol_scale = 1.0
    engine._enable_rsi_vol_gate = False
    engine._core_rsi_ob_filter = 70.0
    engine._core_rsi_os_filter = 30.0

    idx = pd.date_range("2026-01-01", periods=3, freq="h")
    engine._sniper = _SniperMock(idx)
    engine._core = _CoreMock(idx)

    # Dummy dataframe containing required OHLCV columns
    df = pd.DataFrame({
        "open": [1.0, 1.0, 1.0],
        "high": [1.0, 1.0, 1.0],
        "low": [1.0, 1.0, 1.0],
        "close": [1.0, 1.0, 1.0],
        "volume": [100.0, 100.0, 100.0]
    }, index=idx)
    data_map = {"SPY.US": df}

    out = engine.generate(data_map)

    # 1. Format assertions
    assert isinstance(out, dict)
    assert "SPY.US" in out
    assert isinstance(out["SPY.US"], pd.Series)
    assert len(out["SPY.US"]) == 3

    # 2. Logic/Vector merge assertions
    # index 0: sniper_only -> sn.clip(upper=cap) -> 0.225
    # index 1: both -> sn + both_core_frac * co * core_scale -> 0.225 + 0.35 * 0.30 * 0.85 = 0.31425
    # index 2: core_only -> co * core_scale -> 0.30 * 0.85 = 0.255
    expected_weights = [0.225, 0.31425, 0.255]
    np.testing.assert_allclose(out["SPY.US"].tolist(), expected_weights, rtol=1e-5)

    # 3. Confidence and sleeve assertions
    assert "SPY.US" in engine.last_confidence
    assert "SPY.US" in engine.last_sleeve
    assert engine.last_sleeve["SPY.US"].tolist() == [1, 3, 2]  # 1=sniper, 3=both, 2=core


def test_v83_e2e_runner():
    """Verify that v83 runs inside the backtest runner with AlmgrenChrissGlobalEquityEngine."""
    models = dmr.discover_models(["v83_adaptive_regime"])
    assert len(models) == 1, "v83_adaptive_regime model was not discovered"
    
    model = models[0]
    
    # Run a very short backtest on 1 symbol using local source
    res = dmr.run_one(
        model=model,
        mode="daily",
        codes=["SPY.US"],
        start="2026-06-01",
        end="2026-06-10",
        tag="v83_e2e_test",
        force_1d=False,
        reuse=False,
        cash=1000,
        source="local",
        interval="1H",
        extra_cfg={
            "impact_model": "almgren_chriss",
            "ac_eta": 0.1,
            "ac_gamma": 0.0
        }
    )
    
    # Verify execution finished successfully and produced metrics
    assert "error" not in res, f"Backtest failed with error: {res.get('error')}"
    assert res["n"] >= 0
    assert "final" in res
    assert res["final"] > 0
