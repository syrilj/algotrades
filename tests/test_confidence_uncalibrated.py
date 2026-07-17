from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import pandas as pd

from tools.confidence_runtime import evaluate_confidence
from tools.live_plan import macro_regime


class TestConfidenceUncalibrated(unittest.TestCase):
    def setUp(self):
        self.original_env = os.environ.get("CONFIDENCE_ALLOW_UNCALIBRATED")

    def tearDown(self):
        if self.original_env is not None:
            os.environ["CONFIDENCE_ALLOW_UNCALIBRATED"] = self.original_env
        else:
            os.environ.pop("CONFIDENCE_ALLOW_UNCALIBRATED", None)

    def test_evaluate_confidence_fails_closed_by_default(self):
        """By default, a missing calibration file returns ABSTAIN."""
        os.environ.pop("CONFIDENCE_ALLOW_UNCALIBRATED", None)
        freshness = {"available": True, "stale": False}

        # Use a dummy model name that has no json file under runs/calibration/active/
        res = evaluate_confidence(
            raw_probability=0.75,
            model_ok=True,
            setup_ok=True,
            freshness=freshness,
            model="v999_dummy_nonexistent_model",
            horizon="swing"
        )
        self.assertEqual(res["state"], "ABSTAIN")
        self.assertFalse(res["calibration_available"])
        self.assertIn("calibration_artifact_missing", res["reasons"])

    def test_evaluate_confidence_override_remains_research_only(self):
        """The override may expose a score, but it can never size live risk."""
        os.environ["CONFIDENCE_ALLOW_UNCALIBRATED"] = "1"
        freshness = {"available": True, "stale": False}

        res = evaluate_confidence(
            raw_probability=0.75,
            model_ok=True,
            setup_ok=True,
            freshness=freshness,
            model="v999_dummy_nonexistent_model",
            horizon="swing"
        )
        self.assertEqual(res["state"], "ABSTAIN")
        self.assertFalse(res["calibration_available"])
        self.assertIsNone(res["calibrated_probability"])
        self.assertEqual(res["confidence_kind"], "ordinal_confidence_score")
        self.assertIn("ordinal_score_not_probability_calibrated", res["reasons"])


class TestMacroFallback(unittest.TestCase):
    def test_macro_regime_falls_back_to_yfinance(self):
        """A failed LSE request uses the market-data fallback without network I/O."""
        class FailingAdapter:
            def __init__(self):
                self.client = self

            def candles(self, *args, **kwargs):
                raise Exception("LSE simulation failure")

        dates = pd.date_range("2025-01-02", periods=80, freq="B")
        fallback = {
            "QQQ": pd.Series(range(100, 180), index=dates, dtype=float),
            "SPY": pd.Series(range(200, 280), index=dates, dtype=float),
            # Defensive ratio trends down, producing a deterministic risk-on state.
            "XLP": pd.Series([100.0] * len(dates), index=dates),
        }

        with patch("tools.live_plan._daily_close", side_effect=lambda ticker: fallback[ticker]) as mocked:
            res = macro_regime(FailingAdapter())  # type: ignore[arg-type]

        self.assertEqual(mocked.call_count, 3)
        self.assertEqual(res["qqq_trend"], "up")
        self.assertEqual(res["xlp_spy_ratio_state"], "risk_on")
        self.assertIsNone(res["error"])
        self.assertTrue(res["macro_ok"])
