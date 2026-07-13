import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from feedback_loop_arete import passes_promotion_gates, PROMOTION_GATES


class PromotionGateTests(unittest.TestCase):
    def _row(self, ret, dd, sharpe, wr, n, error=None):
        return {
            "id": "test",
            "ret": ret,
            "dd": dd,
            "sharpe": sharpe,
            "wr": wr,
            "n": n,
            "error": error,
        }

    def test_passes_when_candidate_beats_baseline_on_all_locks(self):
        baseline = self._row(0.50, -0.10, 1.50, 0.60, 20)
        candidate = self._row(0.60, -0.08, 1.70, 0.65, 20)
        self.assertTrue(passes_promotion_gates(candidate, baseline))

    def test_fails_when_candidate_worse_return(self):
        baseline = self._row(0.50, -0.10, 1.50, 0.60, 20)
        candidate = self._row(0.40, -0.08, 1.70, 0.65, 20)
        self.assertFalse(passes_promotion_gates(candidate, baseline))

    def test_fails_when_candidate_worse_sharpe(self):
        baseline = self._row(0.50, -0.10, 1.50, 0.60, 20)
        candidate = self._row(0.60, -0.08, 1.40, 0.65, 20)
        self.assertFalse(passes_promotion_gates(candidate, baseline))

    def test_fails_when_drawdown_too_large(self):
        baseline = self._row(0.50, -0.10, 1.50, 0.60, 20)
        candidate = self._row(0.60, -0.30, 1.70, 0.65, 20)
        self.assertFalse(passes_promotion_gates(candidate, baseline))

    def test_fails_when_too_few_trades(self):
        baseline = self._row(0.50, -0.10, 1.50, 0.60, 20)
        candidate = self._row(0.60, -0.08, 1.70, 0.65, 5)
        self.assertFalse(passes_promotion_gates(candidate, baseline))

    def test_absolute_thresholds(self):
        row = self._row(0.10, -0.05, 0.80, 0.50, 20)
        self.assertFalse(passes_promotion_gates(row, row))


if __name__ == "__main__":
    unittest.main()
