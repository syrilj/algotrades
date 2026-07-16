"""Deterministic tests for HAR-RV, surface, VRP features, package scorer."""
from __future__ import annotations

import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from features_vrp import build_features  # noqa: E402
from options_surface import surface_from_chains  # noqa: E402
from rv_har import har_components, latest_har  # noqa: E402
from vol_package_score import pick_recommended, score_packages, score_symbol  # noqa: E402


class TestHAR(unittest.TestCase):
    def test_har_on_synthetic_gbm_like(self):
        rng = np.random.default_rng(42)
        n = 80
        rets = rng.normal(0, 0.01, size=n)
        close = 100 * np.exp(np.cumsum(rets))
        s = pd.Series(close)
        comps = har_components(s)
        self.assertIn("rv_har", comps.columns)
        last = latest_har(s)
        self.assertTrue(math.isfinite(last["rv_har_ann"]))
        self.assertGreater(last["rv_har_ann"], 0.0)
        # Annualized ~1% daily vol → order 0.15–0.25
        self.assertLess(last["rv_har_ann"], 1.0)

    def test_har_for_symbol_from_cache(self):
        from rv_har import har_for_symbol

        spy = ROOT / "data_cache" / "1d" / "SPY.parquet"
        if not spy.exists():
            self.skipTest("SPY parquet missing")
        row = har_for_symbol("SPY")
        self.assertEqual(row["symbol"], "SPY")
        self.assertTrue(math.isfinite(row["rv_har_ann"]))
        self.assertGreater(row["n_bars"], 50)


class TestSurface(unittest.TestCase):
    def test_surface_from_injected_chains(self):
        spot = 100.0
        strikes = np.array([90, 95, 100, 105, 110], dtype=float)
        calls = pd.DataFrame(
            {
                "strike": strikes,
                "impliedVolatility": [0.22, 0.20, 0.18, 0.19, 0.21],
                "bid": [10, 6, 3, 1.5, 0.8],
                "ask": [10.2, 6.2, 3.2, 1.7, 1.0],
                "lastPrice": [10.1, 6.1, 3.1, 1.6, 0.9],
            }
        )
        puts = pd.DataFrame(
            {
                "strike": strikes,
                "impliedVolatility": [0.28, 0.24, 0.18, 0.17, 0.16],
                "bid": [0.8, 1.5, 3, 6, 10],
                "ask": [1.0, 1.7, 3.2, 6.2, 10.2],
                "lastPrice": [0.9, 1.6, 3.1, 6.1, 10.1],
            }
        )
        calls2 = calls.copy()
        calls2["impliedVolatility"] = calls2["impliedVolatility"] + 0.02
        puts2 = puts.copy()
        surface = surface_from_chains(
            spot,
            [
                ("2026-08-15", 21, calls, puts),
                ("2026-09-19", 56, calls2, puts2),
            ],
        )
        self.assertTrue(surface["ok"])
        self.assertAlmostEqual(surface["atm_iv"], 0.18, places=2)
        self.assertEqual(surface["near_dte"], 21)
        self.assertEqual(surface["next_dte"], 56)
        self.assertTrue(math.isfinite(surface["term_slope"]))
        self.assertGreater(surface["skew_25d"], 0.0)  # put wing richer


class TestVRPAndPackages(unittest.TestCase):
    def test_features_with_injected_surface(self):
        # Use real SPY bars + fake surface so offline CI works without network
        spy = ROOT / "data_cache" / "1d" / "SPY.parquet"
        if not spy.exists():
            self.skipTest("SPY parquet missing")
        surface = {
            "ok": True,
            "data_quality": "ok",
            "spot": 500.0,
            "atm_iv": 0.20,
            "term_slope": 0.02,
            "skew_25d": 0.05,
            "near_dte": 21,
            "next_dte": 49,
        }
        row = build_features("SPY", surface=surface, fetch_surface=False)
        self.assertEqual(row["symbol"], "SPY")
        self.assertTrue(math.isfinite(row["rv_har_ann"]))
        self.assertAlmostEqual(row["atm_iv"], 0.20)
        self.assertTrue(math.isfinite(row["iv_rv_spread"]))

    def test_package_scores_rich_iv(self):
        feats = {
            "data_quality": "ok",
            "iv_rv_spread": 0.06,  # IV rich
            "term_slope": 0.03,
            "skew_25d": 0.04,
            "rv_har_ann": 0.15,
        }
        pkgs = score_packages(feats, cost_proxy=0.015)
        by_t = {p["template"]: p for p in pkgs}
        self.assertIn("delta_neutral_short_vol", by_t)
        self.assertGreater(
            by_t["delta_neutral_short_vol"]["edge_after_cost_proxy"],
            by_t["delta_neutral_long_vol"]["edge_after_cost_proxy"],
        )
        rec = pick_recommended(pkgs)
        # short vol may consider but pick_recommended blocks short as sole primary
        self.assertIn(rec["action"], ("consider", "stand_aside"))

    def test_package_scores_cheap_iv(self):
        feats = {
            "data_quality": "ok",
            "iv_rv_spread": -0.06,
            "term_slope": 0.0,
            "skew_25d": 0.0,
            "rv_har_ann": 0.20,
        }
        pkgs = score_packages(feats, cost_proxy=0.015)
        by_t = {p["template"]: p for p in pkgs}
        self.assertEqual(by_t["delta_neutral_long_vol"]["action"], "consider")
        rec = pick_recommended(pkgs)
        self.assertEqual(rec["template"], "delta_neutral_long_vol")
        self.assertEqual(rec["action"], "consider")

    def test_score_symbol_offline(self):
        spy = ROOT / "data_cache" / "1d" / "SPY.parquet"
        if not spy.exists():
            self.skipTest("SPY parquet missing")
        surface = {
            "ok": True,
            "data_quality": "partial",
            "spot": 500.0,
            "atm_iv": 0.12,
            "term_slope": float("nan"),
            "skew_25d": float("nan"),
            "near_dte": 21,
            "next_dte": None,
        }
        out = score_symbol("SPY", surface=surface, fetch_surface=False)
        self.assertTrue(out["ok"])
        self.assertFalse(out["guardrails"]["auto_trade"])
        self.assertTrue(out["guardrails"]["research_only"])
        self.assertIn("packages", out)
        self.assertIn("recommended", out)

    def test_degraded_forces_stand_aside(self):
        feats = {
            "data_quality": "degraded",
            "iv_rv_spread": -0.10,
            "term_slope": 0.05,
            "skew_25d": 0.05,
            "rv_har_ann": 0.15,
        }
        pkgs = score_packages(feats)
        self.assertTrue(all(p["action"] == "stand_aside" for p in pkgs))

    def test_puts_stacking_warning_on_climb(self):
        from vol_package_score import build_warnings, score_packages
        feats = {
            "data_quality": "ok",
            "iv_rv_spread": 0.05,
            "term_slope": 0.0,
            "skew_25d": 0.02,
            "rv_har_ann": 0.20,
            "atm_iv": 0.25,
            "put_call_vol_ratio": 1.8,
            "put_call_oi_ratio": 1.5,
            "put_volume": 9000,
            "call_volume": 4000,
            "spot_ret_5d": 0.04,
            "spot_ret_1d": 0.01,
        }
        pkgs = score_packages(feats)
        warns = build_warnings(feats, pkgs)
        codes = {w["code"] for w in warns}
        self.assertIn("puts_stacking_on_climb", codes)
        danger = [w for w in warns if w["code"] == "puts_stacking_on_climb"][0]
        self.assertEqual(danger["severity"], "danger")
        self.assertIn("dump", danger["message"].lower())


if __name__ == "__main__":
    unittest.main()
