from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "models" / "poc_va_macdha" / "v85_online_contextual" / "signal_engine.py"


def _load_model_module():
    spec = importlib.util.spec_from_file_location("v85_online_contextual_test", MODEL_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _FakeEngine:
    def __init__(self, weight: float, start: int = 810, stop: int = 880) -> None:
        self.weight = weight
        self.start = start
        self.stop = stop

    def generate(self, data_map):
        output = {}
        for code, frame in data_map.items():
            signal = pd.Series(0.0, index=frame.index)
            signal.iloc[self.start : min(self.stop, len(signal))] = self.weight
            output[code] = signal
        return output


def _frame(n: int = 900, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2025-01-02 09:30", periods=n, freq="h")
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0004, 0.003, n)))
    opening = np.r_[close[0], close[:-1]]
    spread = close * 0.002
    return pd.DataFrame(
        {
            "open": opening,
            "high": np.maximum(opening, close) + spread,
            "low": np.minimum(opening, close) - spread,
            "close": close,
            "volume": rng.integers(100_000, 300_000, n),
        },
        index=index,
    )


def _engine_with_fakes(module):
    engine = module.SignalEngine()
    engine._core = _FakeEngine(0.30)
    engine._v45 = _FakeEngine(1.00)
    return engine


def test_frozen_bundle_hash_mismatch_fails_closed(tmp_path):
    module = _load_model_module()
    dependency = tmp_path / "dependency.py"
    dependency.write_text("VALUE = 1\n", encoding="utf-8")
    manifest = {
        "files": [
            {
                "source": "dependency.py",
                "target": "frozen/dependency.py",
                "sha256": "0" * 64,
            }
        ]
    }
    (tmp_path / "DEPENDENCIES.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(RuntimeError, match="hash mismatch"):
        module._verify_bundle(tmp_path)


def test_generate_is_prefix_invariant_and_publishes_ordinal_diagnostics():
    module = _load_model_module()
    target = _frame()
    spy = _frame(seed=11)

    full_engine = _engine_with_fakes(module)
    full = full_engine.generate({"TSLA.US": target, "SPY.US": spy})["TSLA.US"]
    prefix_n = 850
    prefix_engine = _engine_with_fakes(module)
    prefix = prefix_engine.generate(
        {"TSLA.US": target.iloc[:prefix_n], "SPY.US": spy.iloc[:prefix_n]}
    )["TSLA.US"]

    pd.testing.assert_series_equal(prefix, full.iloc[:prefix_n])
    assert full.iloc[820:840].gt(0.0).any()
    assert full_engine.confidence_kind == "ordinal_online_expert_support_not_probability"
    assert full_engine.last_confidence["TSLA.US"].between(0.0, 1.0).all()
    assert set(full_engine.last_expert["TSLA.US"].unique()).issubset(
        {"DUAL", "CORE", "SNIPER", "CASH"}
    )
    assert full_engine.last_readiness_reason["TSLA.US"] == "ready"


def test_symbol_order_and_aliases_do_not_change_outputs():
    module = _load_model_module()
    target = _frame()
    spy = _frame(seed=11)
    engine_a = _engine_with_fakes(module)
    output_a = engine_a.generate({"TSLA.US": target, "SPY.US": spy})
    engine_b = _engine_with_fakes(module)
    output_b = engine_b.generate({"SPY.US": spy, "TSLA": target})

    pd.testing.assert_series_equal(output_a["TSLA.US"], output_b["TSLA"], check_names=False)


def test_missing_context_blocks_new_entries_and_short_history_fails_closed():
    module = _load_model_module()
    target = _frame()
    engine = _engine_with_fakes(module)
    engine._vix_daily = None
    engine._hyg_daily = None
    engine._lqd_daily = None
    output = engine.generate({"TSLA.US": target})["TSLA.US"]

    assert output.eq(0.0).all()
    assert engine.last_context_quality["TSLA.US"].iloc[-1] < 2.0 / 3.0

    short_engine = _engine_with_fakes(module)
    short = short_engine.generate({"TSLA.US": target.iloc[:200]})["TSLA.US"]
    assert short.eq(0.0).all()
    assert "need_at_least" in short_engine.last_readiness_reason["TSLA.US"]
