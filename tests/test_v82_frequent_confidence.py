from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "models" / "poc_va_macdha" / "v82_frequent_confidence" / "signal_engine.py"
SPEC = importlib.util.spec_from_file_location("v82_test_engine", PATH)
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MOD)


class _Balanced:
    def __init__(self, idx: pd.DatetimeIndex) -> None:
        self.idx = idx
        self.last_confidence = {"SPY.US": pd.Series([0.4, 0.8, 0.0], index=idx)}

    def generate(self, data_map):
        return {"SPY.US": pd.Series([0.1, 0.4, 0.0], index=self.idx)}


class _Precision:
    def __init__(self, idx: pd.DatetimeIndex) -> None:
        self.idx = idx

    def generate(self, data_map):
        return {"APLD.US": pd.Series([0.225, 0.0, 0.225], index=self.idx)}


def test_routes_core_satellite_and_excludes_bonds():
    idx = pd.date_range("2026-01-01", periods=3, freq="h")
    data = {
        code: pd.DataFrame({"close": [1.0, 1.1, 1.2]}, index=idx)
        for code in ("SPY.US", "APLD.US", "HYG.US")
    }
    eng = MOD.SignalEngine.__new__(MOD.SignalEngine)
    eng._balanced_symbols = {"SPY.US"}
    eng._excluded_symbols = {"HYG.US"}
    eng._strict_rank_score = 0.75
    eng._max_weight = 0.35
    eng.confidence_kind = "uncalibrated_ordinal_rank_not_probability"
    eng._balanced = _Balanced(idx)
    eng._strict = _Precision(idx)
    eng.last_confidence = {}
    eng.last_tier = {}
    eng.last_strict_tier = {}

    out = eng.generate(data)

    assert out["SPY.US"].tolist() == [0.1, 0.35, 0.0]
    assert out["APLD.US"].tolist() == [0.225, 0.0, 0.225]
    assert out["HYG.US"].eq(0.0).all()
    assert eng.last_tier["SPY.US"].tolist() == [1, 1, 0]
    assert eng.last_tier["APLD.US"].tolist() == [2, 0, 2]
    assert eng.last_strict_tier["APLD.US"].tolist() == [True, False, True]
    assert eng.last_confidence["APLD.US"].tolist() == [0.75, 0.0, 0.75]
    assert "not_probability" in eng.confidence_kind
