from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = ROOT / "models" / "poc_va_macdha" / "v81_high_confidence_boost" / "signal_engine.py"


def _module():
    spec = importlib.util.spec_from_file_location("test_v81_engine", ENGINE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


class _Base:
    def __init__(self, idx: pd.DatetimeIndex):
        self.idx = idx
        self.last_confidence = {"X.US": pd.Series([0.6, 0.7, 0.0], index=idx)}
        self.last_sleeve = {"X.US": pd.Series([2, 1, 0], index=idx)}

    def generate(self, _data_map):
        return {"X.US": pd.Series([0.20, 0.40, 0.0], index=self.idx)}


class _Precision:
    def __init__(self, idx: pd.DatetimeIndex):
        self.idx = idx

    def generate(self, _data_map):
        return {"X.US": pd.Series([0.225, 0.0, 0.225], index=self.idx)}


def _engine(target: float = 0.45):
    mod = _module()
    idx = pd.date_range("2026-01-01", periods=3, freq="h")
    eng = mod.SignalEngine.__new__(mod.SignalEngine)
    eng._target = target
    eng._max_weight = 0.50
    eng._high_conf = 0.90
    eng._allow_orphans = False
    eng._base = _Base(idx)
    eng._precision = _Precision(idx)
    eng.last_confidence = {}
    eng.last_high_confidence = {}
    eng.last_sleeve = {}
    return eng, idx


def test_precision_only_raises_active_v72_position():
    eng, idx = _engine()
    data = {"X.US": pd.DataFrame({"close": [1.0, 1.0, 1.0]}, index=idx)}
    out = eng.generate(data)["X.US"]
    assert out.tolist() == [0.45, 0.40, 0.0]
    assert eng.last_high_confidence["X.US"].tolist() == [True, False, False]
    assert eng.last_confidence["X.US"].tolist() == [0.90, 0.70, 0.0]


def test_precision_target_cannot_exceed_hard_cap():
    eng, idx = _engine(target=0.80)
    data = {"X.US": pd.DataFrame({"close": [1.0, 1.0, 1.0]}, index=idx)}
    out = eng.generate(data)["X.US"]
    assert out.iloc[0] == 0.50
    assert out.abs().max() <= 0.50
