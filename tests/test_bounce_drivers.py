"""Tests for OpEx calendar, QQQ co-move, and driver context helpers."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import bounce_predict as bp  # noqa: E402


class TestOpExCalendar(unittest.TestCase):
    def test_third_friday_known(self):
        # July 2026 third Friday = 2026-07-17
        tf = bp.third_friday(2026, 7)
        self.assertEqual(str(tf.date()), "2026-07-17")
        self.assertEqual(tf.weekday(), 4)

    def test_opex_flag_tomorrow_friday(self):
        # 2026-07-16 is Thursday → tomorrow is weekly OpEx Friday (and monthly)
        flag = bp.opex_session_flag("2026-07-16", look_ahead_days=1)
        self.assertEqual(flag["asof"], "2026-07-16")
        self.assertTrue(flag["tomorrow"]["is_friday"])
        self.assertTrue(flag["tomorrow"]["is_opex_session"])
        self.assertTrue(flag["opex_window"])
        self.assertTrue(any("OpEx" in n or "expiry" in n for n in flag["impact_notes"]))
        self.assertIn("methodology", flag)

    def test_opex_flag_non_friday_midweek(self):
        flag = bp.opex_session_flag("2026-07-14", look_ahead_days=1)  # Tue → Wed
        self.assertFalse(flag["today"]["is_opex_session"])
        self.assertFalse(flag["tomorrow"]["is_opex_session"])
        self.assertFalse(flag["opex_window"])


class TestRollingComove(unittest.TestCase):
    def test_high_tandem_synthetic(self):
        rng = np.random.default_rng(0)
        n = 80
        bench = np.cumsum(rng.normal(0, 0.01, size=n))
        # asset ≈ 1.5 * bench noise
        asset = 1.5 * bench + rng.normal(0, 0.001, size=n)
        idx = pd.date_range("2024-01-01", periods=n, freq="B")
        out = bp.rolling_comove(
            pd.Series(np.exp(asset), index=idx),
            pd.Series(np.exp(bench), index=idx),
            window=20,
        )
        self.assertTrue(out["ok"])
        self.assertIsNotNone(out["corr"])
        self.assertGreater(out["corr"], 0.55)
        self.assertEqual(out["tandem"], "high_tandem")
        self.assertIn(out["same_day_direction"], {"together", "divergent", "flat"})

    def test_insufficient_overlap(self):
        idx = pd.date_range("2024-01-01", periods=5, freq="B")
        out = bp.rolling_comove(
            pd.Series(range(5), index=idx, dtype=float),
            pd.Series(range(5), index=idx, dtype=float),
            window=20,
        )
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "insufficient_overlap")


class TestDriverContext(unittest.TestCase):
    def test_tsla_driver_prior_and_missing_options(self):
        idx = pd.date_range("2024-01-01", periods=40, freq="B")
        # mild series so co-move may fail without bench cache — still structure ok
        s = pd.Series(np.linspace(100, 110, 40), index=idx)
        ctx = bp.symbol_driver_context(
            "TSLA",
            asset_close=s,
            asof="2026-07-16",
            gex=None,
            options=None,
            spot=105.0,
        )
        self.assertEqual(ctx["symbol"], "TSLA")
        self.assertEqual(ctx["driver_prior"]["primary_benchmark"], "QQQ")
        self.assertIn("Nasdaq", ctx["summary"] or ctx["driver_prior"]["thesis"])
        self.assertFalse(ctx["options_pressure"]["available"])
        self.assertEqual(ctx["options_pressure"]["note"], "options_flow_unavailable")
        self.assertFalse(ctx["gex_pressure"]["available"])
        self.assertTrue(ctx["opex"]["opex_window"])  # Thu→Fri Jul 16-17 2026
        self.assertIn("opex", ctx)

    def test_infq_prior_not_ionq(self):
        ctx = bp.symbol_driver_context("INFQ", asset_close=None, asof="2026-07-16")
        self.assertIn("not IONQ", ctx["driver_prior"]["thesis"])
        r = bp.resolve_symbol("INFQ")
        self.assertEqual(r["resolved"], "INFQ")
        self.assertIn("infq_stock", r["note"])

    def test_options_and_gex_when_present(self):
        idx = pd.date_range("2024-01-01", periods=30, freq="B")
        s = pd.Series(np.linspace(200, 210, 30), index=idx)
        ctx = bp.symbol_driver_context(
            "TSLA",
            asset_close=s,
            asof="2026-07-13",  # Mon — not opex window for look-ahead Tue
            options={"calls": 8, "puts": 2, "pc": 0.4},
            gex={"call_wall": 220.0, "put_wall": 200.0, "label": "positive_gex_pin"},
            spot=208.0,
        )
        self.assertTrue(ctx["options_pressure"]["available"])
        self.assertEqual(ctx["options_pressure"]["flow_bias"], "call_heavy")
        self.assertTrue(ctx["gex_pressure"]["available"])
        self.assertIsNotNone(ctx["gex_pressure"]["near_wall"])
        self.assertTrue(any("options flow" in m or "GEX" in m or "corr=" in m for m in ctx["what_moves_this"]))


class TestProxyComoveHonesty(unittest.TestCase):
    def test_asset_is_proxy_never_high_tandem(self):
        """Thin ADR using SOXX bars must not invent corr=1 vs SOXX."""
        idx = pd.date_range("2024-01-01", periods=40, freq="B")
        # Even if we pass a real-looking series, asset_is_proxy=True forces refuse
        s = pd.Series(np.linspace(150, 160, 40), index=idx)
        ctx = bp.symbol_driver_context(
            "SKHY",
            asset_close=s,
            asof="2026-07-16",
            asset_is_proxy=True,
            proxy_symbol="SOXX",
            options={"calls": 5, "puts": 2, "pc": 0.5},
            spot=155.0,
        )
        com = ctx["comove"]
        self.assertFalse(com["ok"])
        self.assertEqual(com["error"], "proxy_self_or_unavailable")
        self.assertIsNone(com.get("corr"))
        self.assertIsNone(com.get("tandem"))
        self.assertNotEqual(com.get("tandem"), "high_tandem")
        # what_moves_this must not claim high tandem corr
        moves = " ".join(ctx.get("what_moves_this") or [])
        self.assertNotIn("high_tandem", moves)
        self.assertNotIn("corr=1", moves)
        self.assertTrue(
            any("proxy" in m.lower() or "unavailable" in m.lower() for m in (ctx.get("what_moves_this") or []))
            or com.get("error") == "proxy_self_or_unavailable"
        )

    def test_self_identical_series_refused_even_without_flag(self):
        """If asset series is nearly identical to benchmark returns, refuse co-move."""
        soxx = bp.load_ohlcv("SOXX", prefer_live=False)
        if soxx is None or len(soxx) < 40:
            self.skipTest("SOXX cache missing")
        close = soxx[[c for c in soxx.columns if c.lower() == "close"][0]].astype(float).tail(60)
        # Measure SKHY-named series that is actually SOXX prices → self-proxy leak
        ctx = bp.symbol_driver_context(
            "SKHY",
            asset_close=close,
            asof="2026-07-16",
            asset_is_proxy=False,
            proxy_symbol=None,
            spot=float(close.iloc[-1]),
        )
        com = ctx["comove"]
        # Either insufficient or proxy_self — never high_tandem with corr≈1 as truth
        if com.get("ok"):
            self.assertLess(abs(float(com["corr"])), 0.995)
        else:
            self.assertIn(com.get("error"), {"proxy_self_or_unavailable", "insufficient_overlap", "no_asset_series"})


class TestPredictUsesDriverFields(unittest.TestCase):
    def test_predict_symbol_schema_without_live(self):
        """--no-live still attaches opex + comove structure from OHLCV."""
        if not bp.DEFAULT_ARTIFACT.exists():
            self.skipTest("artifact missing")
        out = bp.predict_symbol("TSLA", enrich_live=False, target_price=397.5)
        if not out.get("ok"):
            self.skipTest(out.get("error"))
        ctx = out.get("context") or {}
        self.assertIn("drivers", ctx)
        self.assertIn("opex", ctx)
        self.assertIn("comove", ctx)
        self.assertIn("what_moves_this", ctx)
        # TSLA co-move block should name QQQ when data available
        com = ctx.get("comove") or {}
        if com.get("ok"):
            self.assertEqual(com.get("benchmark"), "QQQ")
        self.assertIn("opex_window", ctx.get("opex") or {})
        self.assertEqual(out["symbol_resolution"]["resolved"], "TSLA")

    def test_skhy_proxy_path_comove_not_fake_tandem(self):
        """Shipped predict_symbol for thin SKHY must not report corr=1 high_tandem."""
        if not bp.DEFAULT_ARTIFACT.exists():
            self.skipTest("artifact missing")
        out = bp.predict_symbol("SKHY", enrich_live=False, target_price=180.0)
        if not out.get("ok"):
            self.skipTest(out.get("error"))
        com = (out.get("context") or {}).get("comove") or {}
        # Thin history → proxy: comove must be unavailable, not invented tandem
        if "proxy" in str(out.get("history_note") or ""):
            self.assertFalse(com.get("ok"))
            self.assertEqual(com.get("error"), "proxy_self_or_unavailable")
            self.assertIsNone(com.get("corr"))
            self.assertIsNone(com.get("tandem"))
            take = out.get("live_take") or ""
            self.assertNotIn("corr=1", take)
            self.assertNotIn("corr=1.0", take)
            notes = (out.get("context") or {}).get("notes") or []
            self.assertTrue(
                any("comove_unavailable" in n or "proxy" in n for n in notes)
                or "proxy" in str(out.get("history_note"))
            )


if __name__ == "__main__":
    unittest.main()
