"""Unit tests for beat-champion multi-lock promotion gates."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from feedback_loop_beat_champion import (  # noqa: E402
    PROMOTION_GATES,
    passes_promotion_gates,
)


def _row(**kwargs):
    base = {
        "id": "x",
        "ret": 1.0,
        "dd": -0.10,
        "sharpe": 2.5,
        "n": 50,
        "wr": 0.65,
    }
    base.update(kwargs)
    return base


class TestPromotionGates(unittest.TestCase):
    def test_promote_when_all_better(self):
        baseline = _row(ret=1.0, dd=-0.13, sharpe=2.5, n=40)
        cand = _row(ret=1.05, dd=-0.12, sharpe=2.6, n=40)
        ok, reason = passes_promotion_gates(cand, baseline)
        self.assertTrue(ok, reason)
        self.assertEqual(reason, "multi_lock_ok")

    def test_fail_when_ret_not_strictly_better(self):
        baseline = _row(ret=1.0, sharpe=2.5, dd=-0.13)
        cand = _row(ret=1.0, sharpe=2.6, dd=-0.12)
        ok, reason = passes_promotion_gates(cand, baseline)
        self.assertFalse(ok)
        self.assertIn("ret_not_gt", reason)

    def test_fail_when_sharpe_not_better(self):
        baseline = _row(ret=1.0, sharpe=2.5, dd=-0.13)
        cand = _row(ret=1.1, sharpe=2.5, dd=-0.12)
        ok, reason = passes_promotion_gates(cand, baseline)
        self.assertFalse(ok)
        self.assertIn("sharpe_not_gt", reason)

    def test_fail_when_dd_materially_worse(self):
        baseline = _row(ret=1.0, sharpe=2.5, dd=-0.10)
        cand = _row(ret=1.1, sharpe=2.6, dd=-0.20)
        ok, reason = passes_promotion_gates(cand, baseline)
        self.assertFalse(ok)
        self.assertIn("dd_worse", reason)

    def test_dd_slack_allows_small_worsening(self):
        baseline = _row(ret=1.0, sharpe=2.5, dd=-0.10)
        slack = PROMOTION_GATES["dd_slack"]
        cand = _row(ret=1.1, sharpe=2.6, dd=-(0.10 + slack))
        ok, reason = passes_promotion_gates(cand, baseline)
        self.assertTrue(ok, reason)

    def test_fail_low_n(self):
        baseline = _row(n=40)
        cand = _row(ret=2.0, sharpe=3.0, dd=-0.05, n=5)
        ok, reason = passes_promotion_gates(cand, baseline, min_n=10)
        self.assertFalse(ok)
        self.assertIn("n=", reason)

    def test_fail_on_error(self):
        baseline = _row()
        cand = _row(error="boom")
        ok, reason = passes_promotion_gates(cand, baseline)
        self.assertFalse(ok)
        self.assertIn("candidate_error", reason)

    def test_fail_absolute_sharpe_floor(self):
        baseline = _row(ret=0.1, sharpe=0.5, dd=-0.05, n=40)
        cand = _row(ret=0.2, sharpe=0.9, dd=-0.04, n=40)
        ok, reason = passes_promotion_gates(cand, baseline)
        self.assertFalse(ok)
        self.assertIn("sharpe", reason)


if __name__ == "__main__":
    unittest.main()
