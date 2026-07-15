from __future__ import annotations

import sys
import tempfile
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from evolve.v48_validation import (  # noqa: E402
    dependency_hashes,
    load_signal_engine,
    run_causal_invariance_suite,
    validate_data_contract,
)
from train_v39d_causal_meta import META_FEATURES, train  # noqa: E402
from evolve.v48_protocol import deflated_sharpe_ratio, fold_gate, probability_of_backtest_overfitting  # noqa: E402


def _frame(seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2025-01-02 09:30", periods=180, freq="h")
    close = 100 + np.cumsum(rng.normal(0.04, 0.8, len(index)))
    open_ = close + rng.normal(0.0, 0.15, len(index))
    high = np.maximum(open_, close) + rng.uniform(0.05, 0.6, len(index))
    low = np.minimum(open_, close) - rng.uniform(0.05, 0.6, len(index))
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": rng.integers(1000, 5000, len(index))},
        index=index,
    )


class V48RegimeBarbellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        model_dir = ROOT / "models" / "poc_va_macdha" / "v48_regime_barbell"
        cls.engine_class = load_signal_engine(model_dir)
        cls.data = {"TSLA.US": _frame(1), "QQQ.US": _frame(2)}

    def test_causal_engine_passes_all_invariance_checks(self):
        result = run_causal_invariance_suite(self.engine_class, self.data)
        self.assertEqual(set(result), {"prefix", "future_perturbation", "symbol_order", "repeatability"})
        self.assertTrue(all(result.values()))

    def test_feedback_policy_remains_causal(self):
        def feedback_engine():
            engine = self.engine_class()
            engine.policy = "regime_feedback"
            engine.strict_regime = False
            return engine

        result = run_causal_invariance_suite(feedback_engine, self.data)
        self.assertTrue(all(result.values()))

    def test_precision_challenger_is_causal_and_does_not_reenter_rejected_episodes(self):
        precision = load_signal_engine(ROOT / "models" / "poc_va_macdha" / "v49_precision_trend")
        result = run_causal_invariance_suite(precision, self.data)
        self.assertTrue(all(result.values()))
        engine = precision()
        base = pd.Series([0.0, 0.6, 0.6, 0.0, 0.4, 0.4], index=pd.RangeIndex(6))
        gate = pd.Series([False, False, True, False, True, True], index=base.index)
        expected = pd.Series([0.0, 0.0, 0.0, 0.0, 0.4, 0.4], index=base.index)
        pd.testing.assert_series_equal(engine._retain_accepted_episodes(base, gate), expected)

    def test_model_snapshot_hashes_include_vendored_teacher(self):
        hashes = dependency_hashes(ROOT / "models" / "poc_va_macdha" / "v48_regime_barbell")
        self.assertIn("signal_engine.py", hashes)
        self.assertIn("v48_teachers.py", hashes)

    def test_data_contract_rejects_invalid_high(self):
        broken = _frame(3)
        broken.iloc[4, broken.columns.get_loc("high")] = broken.iloc[4][["open", "close", "low"]].min() - 1
        with self.assertRaises(ValueError):
            validate_data_contract({"TSLA.US": broken})

    def test_fold_local_meta_trainer_writes_a_pinned_artifact(self):
        rows = []
        for i in range(60):
            row = {
                "timestamp": f"2025-01-{1 + i // 4:02d} 10:00:00",
                "exit_timestamp": f"2025-01-{1 + i // 4:02d} 14:00:00",
                "label": i % 2,
            }
            row.update({f"f_{feature}": float((i + n) % 5) for n, feature in enumerate(META_FEATURES)})
            rows.append(row)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ledger = root / "candidates.csv"
            pd.DataFrame(rows).to_csv(ledger, index=False)
            metadata = train(ledger, root / "model", "2025-01-31")
            self.assertEqual(metadata["rows"], 60)
            self.assertTrue((root / "model" / "meta_xgb_fold.json").exists())

    def test_fold_protocol_requires_stability_and_corrects_for_trials(self):
        rows = [{"ret": 0.05, "dd": -0.10, "sharpe": 1.2, "n": 30} for _ in range(4)]
        verdict = fold_gate(rows, global_trials=7)
        self.assertTrue(verdict["passed"])
        self.assertGreaterEqual(verdict["dsr"], 0.95)
        scores = pd.DataFrame({"f1": [0.4, 0.1], "f2": [0.3, 0.1], "f3": [0.2, 0.1], "f4": [0.1, 0.1]}, index=["a", "b"])
        self.assertLessEqual(probability_of_backtest_overfitting(scores), 1.0)
        self.assertGreater(deflated_sharpe_ratio(1.5, 100, 1), 0.95)


if __name__ == "__main__":
    unittest.main()
