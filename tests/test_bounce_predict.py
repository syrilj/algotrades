"""Unit tests for bounce_predict pure transform + symbol resolution."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import bounce_predict as bp  # noqa: E402


class TestSymbolResolution(unittest.TestCase):
    def test_infq_stays_native_by_default(self):
        r = bp.resolve_symbol("INFQ")
        self.assertEqual(r["resolved"], "INFQ")
        self.assertFalse(r["alias_applied"])
        self.assertIn("infq_stock", r["note"])

    def test_infq_alias_explicit(self):
        r = bp.resolve_symbol("INFQ", apply_desk_alias=True)
        self.assertEqual(r["resolved"], "IONQ")
        self.assertTrue(r["alias_applied"])
        self.assertEqual(r["alias_from"], "INFQ")

    def test_tsla_normalize(self):
        r = bp.resolve_symbol(" tsla.us ")
        self.assertEqual(r["resolved"], "TSLA")


class TestFeaturesAndPredict(unittest.TestCase):
    def _synth_ohlcv(self, n: int = 120, seed: int = 0) -> pd.DataFrame:
        rng = np.random.default_rng(seed)
        rets = rng.normal(0, 0.015, size=n)
        close = 100 * np.exp(np.cumsum(rets))
        high = close * (1 + rng.uniform(0.001, 0.02, size=n))
        low = close * (1 - rng.uniform(0.001, 0.02, size=n))
        open_ = close * (1 + rng.normal(0, 0.005, size=n))
        vol = rng.integers(1_000_000, 5_000_000, size=n)
        idx = pd.date_range("2024-01-01", periods=n, freq="B")
        return pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": vol},
            index=idx,
        )

    def test_feature_row_finite_quality(self):
        df = self._synth_ohlcv()
        row = bp.feature_row_at(df, -1)
        self.assertEqual(set(row.keys()), set(bp.FEATURE_NAMES))
        q = bp.feature_quality(row)
        self.assertGreaterEqual(q, 0.7)

    def test_predict_from_features_bounds_and_abstain(self):
        # Minimal artifact: zeros → raw ~0.5 after sigmoid of intercept
        art = bp.BounceArtifact(
            coef=[0.0] * len(bp.FEATURE_NAMES),
            intercept=0.0,
            feature_names=list(bp.FEATURE_NAMES),
            feature_mean=[0.0] * len(bp.FEATURE_NAMES),
            feature_std=[1.0] * len(bp.FEATURE_NAMES),
            isotonic={"x": [0.2, 0.5, 0.8], "y": [0.25, 0.5, 0.75]},
            high_conf_enter=0.70,
            high_conf_watch=0.60,
            horizon=5,
            train_symbols=["TEST"],
            train_end=None,
            n_train=100,
        )
        # low quality features → abstain
        bad = {k: float("nan") for k in bp.FEATURE_NAMES}
        out = bp.predict_from_features(bad, art)
        self.assertTrue(out["ok"])
        self.assertGreaterEqual(out["p_bounce"], 0.0)
        self.assertLessEqual(out["p_bounce"], 1.0)
        self.assertEqual(out["confidence_state"], "ABSTAIN")
        self.assertTrue(out["abstain"])
        self.assertIn(out["direction"], {"up", "down", "sideways"})

        # good quality, mid probability
        good = {k: 0.0 for k in bp.FEATURE_NAMES}
        good["ret_1d"] = -0.02
        good["range_pos_5d"] = 0.2
        good["rsi_14"] = 0.35
        out2 = bp.predict_from_features(good, art)
        self.assertTrue(0.0 <= out2["p_bounce"] <= 1.0)
        self.assertIn(out2["direction"], {"up", "down", "sideways"})

    def test_predict_high_state_when_calibrated_high(self):
        art = bp.BounceArtifact(
            coef=[0.0] * len(bp.FEATURE_NAMES),
            intercept=2.2,  # sigmoid ~0.9
            feature_names=list(bp.FEATURE_NAMES),
            feature_mean=[0.0] * len(bp.FEATURE_NAMES),
            feature_std=[1.0] * len(bp.FEATURE_NAMES),
            isotonic={"x": [0.5, 0.9], "y": [0.5, 0.88]},
            high_conf_enter=0.70,
            high_conf_watch=0.60,
            horizon=5,
            train_symbols=["TEST"],
            train_end=None,
            n_train=100,
        )
        good = {k: 0.0 for k in bp.FEATURE_NAMES}
        for i, k in enumerate(bp.FEATURE_NAMES[:10]):
            good[k] = 0.01 * (i + 1)
        # Must be a down day — train/eval HIGH band only covers ret_1d < 0
        good["ret_1d"] = -0.02
        out = bp.predict_from_features(good, art)
        self.assertGreaterEqual(out["p_bounce"], 0.70)
        self.assertEqual(out["confidence_state"], "HIGH")
        self.assertFalse(out["abstain"])
        self.assertTrue(out["down_day_context"])
        self.assertEqual(out["direction"], "up")

    def test_up_day_cannot_claim_high_even_if_score_high(self):
        """OOD guard: ret_1d>=0 is outside down-day train context → never HIGH."""
        art = bp.BounceArtifact(
            coef=[0.0] * len(bp.FEATURE_NAMES),
            intercept=3.0,  # raw p ~0.95
            feature_names=list(bp.FEATURE_NAMES),
            feature_mean=[0.0] * len(bp.FEATURE_NAMES),
            feature_std=[1.0] * len(bp.FEATURE_NAMES),
            isotonic={"x": [0.5, 0.95], "y": [0.5, 0.92]},
            high_conf_enter=0.70,
            high_conf_watch=0.60,
            horizon=5,
            train_symbols=["TEST"],
            train_end=None,
            n_train=100,
        )
        # Realistic good-quality row on a big up day (e.g. TSLA +11.9%)
        feats = {k: 0.0 for k in bp.FEATURE_NAMES}
        feats["ret_1d"] = 0.119
        feats["ret_3d"] = 0.08
        feats["ret_5d"] = 0.05
        feats["range_pos_5d"] = 0.9
        feats["range_pos_20d"] = 0.85
        feats["rsi_14"] = 0.72
        feats["atr_pct_14"] = 0.03
        feats["vol_z_20"] = 1.2
        feats["above_sma20"] = 1.0
        feats["above_sma50"] = 1.0
        feats["close_loc"] = 0.8
        feats["intraday_range_pct"] = 0.04
        feats["body_pct"] = 0.02
        self.assertGreaterEqual(bp.feature_quality(feats), 0.7)

        out = bp.predict_from_features(feats, art)
        self.assertTrue(out["ok"])
        self.assertGreaterEqual(out["p_bounce"], 0.70)  # score can still be high
        self.assertEqual(out["confidence_state"], "ABSTAIN")
        self.assertTrue(out["abstain"])
        self.assertFalse(out["down_day_context"])
        self.assertTrue(
            any("not_down_day" in r or "ood" in r for r in out["abstain_reasons"]),
            out["abstain_reasons"],
        )

    def test_missing_ret_1d_cannot_claim_high(self):
        art = bp.BounceArtifact(
            coef=[0.0] * len(bp.FEATURE_NAMES),
            intercept=2.5,
            feature_names=list(bp.FEATURE_NAMES),
            feature_mean=[0.0] * len(bp.FEATURE_NAMES),
            feature_std=[1.0] * len(bp.FEATURE_NAMES),
            isotonic={"x": [0.5, 0.9], "y": [0.5, 0.88]},
            high_conf_enter=0.70,
            high_conf_watch=0.60,
            horizon=5,
            train_symbols=["TEST"],
            train_end=None,
            n_train=50,
        )
        feats = {k: 0.0 for k in bp.FEATURE_NAMES}
        feats["ret_1d"] = float("nan")
        # keep quality high via other core fields
        for k in (
            "ret_3d",
            "ret_5d",
            "range_pos_5d",
            "range_pos_20d",
            "atr_pct_14",
            "vol_z_20",
            "rsi_14",
            "close_loc",
        ):
            feats[k] = 0.1
        out = bp.predict_from_features(feats, art)
        self.assertEqual(out["confidence_state"], "ABSTAIN")
        self.assertTrue(out["abstain"])
        self.assertFalse(out["down_day_context"])

    def test_target_hit_scales_with_difficulty(self):
        art = bp.BounceArtifact(
            coef=[0.0] * len(bp.FEATURE_NAMES),
            intercept=1.0,
            feature_names=list(bp.FEATURE_NAMES),
            feature_mean=[0.0] * len(bp.FEATURE_NAMES),
            feature_std=[1.0] * len(bp.FEATURE_NAMES),
            isotonic={"x": [0.5, 0.8], "y": [0.5, 0.75]},
            high_conf_enter=0.70,
            high_conf_watch=0.55,
            horizon=5,
            train_symbols=["TEST"],
            train_end=None,
            n_train=10,
        )
        feats = {k: 0.0 for k in bp.FEATURE_NAMES}
        easy = bp.predict_from_features(feats, art, target_ret=0.01, horizon=5)
        hard = bp.predict_from_features(feats, art, target_ret=0.15, horizon=5)
        self.assertIsNotNone(easy["p_target_hit"])
        self.assertIsNotNone(hard["p_target_hit"])
        self.assertGreater(easy["p_target_hit"], hard["p_target_hit"])

    def test_no_lookahead_in_feature_frame(self):
        """Features at bar i must not depend on close[i+1]."""
        df = self._synth_ohlcv(80, seed=1)
        f0 = bp.feature_frame_from_ohlcv(df)
        # mutate future bar
        df2 = df.copy()
        df2.iloc[-1, df2.columns.get_loc("close")] = df2.iloc[-1]["close"] * 1.5
        f1 = bp.feature_frame_from_ohlcv(df2)
        # penultimate row features should match (only last bar changed)
        a = f0.iloc[-2][bp.FEATURE_NAMES[:15]].to_numpy(dtype=float)
        b = f1.iloc[-2][bp.FEATURE_NAMES[:15]].to_numpy(dtype=float)
        np.testing.assert_allclose(a, b, equal_nan=True, rtol=1e-9, atol=1e-9)


class TestArtifactRoundtrip(unittest.TestCase):
    def test_default_artifact_loads_after_train(self):
        path = bp.DEFAULT_ARTIFACT
        if not path.exists():
            self.skipTest("artifact missing — run bounce_predict --train")
        art = bp.load_artifact(path)
        self.assertEqual(len(art.coef), len(bp.FEATURE_NAMES))
        self.assertGreater(art.n_train, 100)
        # predict via real entry with no live deps
        out = bp.predict_symbol("TSLA", enrich_live=False, artifact=art, target_price=397.5)
        self.assertTrue(out["ok"])
        self.assertIn(out["direction"], {"up", "down", "sideways"})
        self.assertGreaterEqual(out["p_bounce"], 0.0)
        self.assertLessEqual(out["p_bounce"], 1.0)
        self.assertEqual(out["symbol"], "TSLA")
        self.assertIn("symbol_resolution", out)

    def test_oos_artifact_exists(self):
        p = bp.EVAL_PATH
        if not p.exists():
            self.skipTest("OOS artifact missing")
        doc = json.loads(p.read_text())
        self.assertTrue(doc.get("ok"))
        self.assertIn("holdout_metrics", doc)
        self.assertIn("brier", doc["holdout_metrics"])
        self.assertIn("high_confidence_band", doc)
        self.assertIn("hit_rate", doc["high_confidence_band"])


if __name__ == "__main__":
    unittest.main()
