"""v40_arete_pro — v39b equity base + Arete Trading overlay filters.

Wraps the current champion equity engine (v39b_live_adapt) and scales its
position signals by an Arete-inspired confluence score.

Arete principles used:
- 12/22/55 EMA cloud: close must be above the 22 and 55 day EMAs for a swing
  long to have institutional support.
- 61.8 / 78.6 Fib retracements: a pullback that holds the 78.6% level is
  acceptable; below it is rejected.
- SOX/SOXL health: if the semiconductor index and levered proxy lose their
  55-day EMA, avoid new growth/semiconductor longs.
- VIX / VXX proxy: elevated volatility (>1.5x its 20-day EMA or >40) reduces
  size.
- Relative strength: the target must be leading SPY and QQQ over the lookback.
- Volume: a surge above the 20-bar SMA is a breakout confirmation.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Set

import numpy as np
import pandas as pd


# Target symbols to trade (growth / semis / high-beta).
TARGET_CODES: Set[str] = {"TSLA.US", "MU.US", "IONQ.US", "APLD.US"}

# Context codes we can pull from data_map for Arete overlays.
CONTEXT_CODES: Set[str] = {
    "SPY.US",
    "XLP.US",
    "QQQ.US",
    "SMH.US",
    "SOXL.US",
    "VXX.US",
    "IWM.US",
    "XLK.US",
    "XLY.US",
    "XLU.US",
}


def _load_base_engine():
    """Import the v39b_live_adapt SignalEngine without placing it on sys.path."""
    here = Path(__file__).resolve().parent
    candidates = [
        here.parents[1] / "v39b_live_adapt" / "signal_engine.py",
        Path("/Users/syriljacob/Desktop/TradingAlgoWork/models/poc_va_macdha/v39b_live_adapt/signal_engine.py"),
    ]
    for c in candidates:
        if c.exists():
            mod_name = "v39b_base_arete"
            spec = importlib.util.spec_from_file_location(mod_name, c)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            assert spec.loader is not None
            spec.loader.exec_module(mod)
            return mod.SignalEngine()
    raise FileNotFoundError("v39b_live_adapt engine not found")


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _load_hunt_config() -> Dict[str, Any]:
    cfg: Dict[str, Any] = {}
    for cand in (
        Path(__file__).resolve().parent / "hunt_config.json",
        Path(__file__).resolve().parents[1] / "hunt_config.json",
    ):
        if cand.exists():
            try:
                cfg = json.loads(cand.read_text(encoding="utf-8"))
            except Exception:
                pass
            break
    return cfg


class SignalEngine:
    """v40 Arete overlay on top of v39b live-adapt equity engine."""

    def __init__(self):
        self._base = _load_base_engine()
        cfg = _load_hunt_config()

        self._enable_ma = bool(cfg.get("enable_ma", True))
        self._enable_fib = bool(cfg.get("enable_fib", True))
        self._enable_sox = bool(cfg.get("enable_sox", True))
        self._enable_vix = bool(cfg.get("enable_vix", True))
        self._enable_rs = bool(cfg.get("enable_rs", True))
        self._enable_vol = bool(cfg.get("enable_vol", True))

        self._ma_fast = int(cfg.get("ma_fast", 22))
        self._ma_slow = int(cfg.get("ma_slow", 55))
        self._fib_look = int(cfg.get("fib_look", 50))
        self._rs_look = int(cfg.get("rs_look", 5))
        self._vol_sma = int(cfg.get("vol_sma", 20))
        self._vol_surge = float(cfg.get("vol_surge", 1.25))

    def _daily_close(self, df: Optional[pd.DataFrame]) -> Optional[pd.Series]:
        if df is None or df.empty:
            return None
        d = df["close"].copy()
        if getattr(d.index, "tz", None) is not None:
            d.index = d.index.tz_localize(None)
        return d.resample("1D").last().dropna()

    def _reindexed_daily(self, daily: Optional[pd.Series], idx: pd.Index) -> pd.Series:
        if daily is None or daily.empty:
            return pd.Series(np.nan, index=idx)
        return daily.reindex(idx, method="ffill")

    def _arete_mult(self, code: str, df: pd.DataFrame, data_map: Dict[str, pd.DataFrame]) -> pd.Series:
        """Return a 0-1 multiplier for each bar of the target symbol."""
        idx = df.index
        close = df["close"].astype(float)

        # Daily close series for slower overlays (avoids intraday noise).
        daily = self._daily_close(df)
        if daily is None or len(daily) < max(self._ma_slow, self._fib_look) + 2:
            return pd.Series(1.0, index=idx)

        # MA gate (close above 22/55 EMA on daily bars).
        ema_fast = _ema(daily, self._ma_fast).shift(1)
        ema_slow = _ema(daily, self._ma_slow).shift(1)

        # Fib support from last N daily highs/lows.
        high_look = daily.rolling(self._fib_look, min_periods=20).max().shift(1)
        low_look = daily.rolling(self._fib_look, min_periods=20).min().shift(1)
        fib_range = high_look - low_look
        fib_618 = high_look - 0.618 * fib_range
        fib_786 = high_look - 0.786 * fib_range

        # Context daily series.
        spy = self._daily_close(data_map.get("SPY.US"))
        qqq = self._daily_close(data_map.get("QQQ.US"))
        smh = self._daily_close(data_map.get("SMH.US"))
        soxl = self._daily_close(data_map.get("SOXL.US"))
        vxx = self._daily_close(data_map.get("VXX.US"))

        # Relative strength.
        target_ret = daily.pct_change(self._rs_look).shift(1)
        spy_ret = spy.pct_change(self._rs_look).shift(1) if spy is not None else None
        qqq_ret = qqq.pct_change(self._rs_look).shift(1) if qqq is not None else None
        smh_ret = smh.pct_change(self._rs_look).shift(1) if smh is not None else None

        # SOX health.
        smh_ema55 = _ema(smh, 55).shift(1) if smh is not None else None
        soxl_ema55 = _ema(soxl, 55).shift(1) if soxl is not None else None

        # VXX proxy for VIX.
        vxx_ema20 = _ema(vxx, 20).shift(1) if vxx is not None else None

        # Volume surge on the original bar timeframe.
        vol = df["volume"].astype(float)
        vol_sma = vol.rolling(self._vol_sma, min_periods=10).mean().shift(1)
        vol_surge = vol > (self._vol_surge * vol_sma)

        # Reindex daily overlays to the original bar index.
        ema_fast_h = self._reindexed_daily(ema_fast, idx)
        ema_slow_h = self._reindexed_daily(ema_slow, idx)
        fib_618_h = self._reindexed_daily(fib_618, idx)
        fib_786_h = self._reindexed_daily(fib_786, idx)

        target_ret_h = self._reindexed_daily(target_ret, idx)
        spy_ret_h = self._reindexed_daily(spy_ret, idx) if spy_ret is not None else None
        qqq_ret_h = self._reindexed_daily(qqq_ret, idx) if qqq_ret is not None else None
        smh_ret_h = self._reindexed_daily(smh_ret, idx) if smh_ret is not None else None

        smh_ema55_h = self._reindexed_daily(smh_ema55, idx) if smh_ema55 is not None else None
        soxl_ema55_h = self._reindexed_daily(soxl_ema55, idx) if soxl_ema55 is not None else None
        vxx_ema20_h = self._reindexed_daily(vxx_ema20, idx) if vxx_ema20 is not None else None

        # MA gate.
        if self._enable_ma:
            ma_gate = (close > ema_slow_h) & (close > ema_fast_h)
        else:
            ma_gate = pd.Series(True, index=idx)

        # Fib gate + multiplier.
        if self._enable_fib:
            above_786 = (close > fib_786_h).fillna(True)
            above_618 = (close > fib_618_h).fillna(True)
            fib_gate = above_786
            fib_mult = (above_618.astype(float) * 0.5 + above_786.astype(float) * 0.5).clip(0.0, 1.0)
        else:
            fib_gate = pd.Series(True, index=idx)
            fib_mult = pd.Series(1.0, index=idx)

        # SOX health gate.
        sox_gate = pd.Series(True, index=idx)
        if self._enable_sox:
            if smh is not None and smh_ema55_h is not None:
                smh_ok = (smh.reindex(idx, method="ffill") > smh_ema55_h).fillna(True)
                sox_gate = sox_gate & smh_ok
            if soxl is not None and soxl_ema55_h is not None:
                soxl_ok = (soxl.reindex(idx, method="ffill") > soxl_ema55_h).fillna(True)
                sox_gate = sox_gate & soxl_ok

        # VIX proxy multiplier.
        vix_mult = pd.Series(1.0, index=idx)
        if self._enable_vix and vxx is not None and vxx_ema20_h is not None:
            vxx_h = vxx.reindex(idx, method="ffill")
            vix_high = (vxx_h > 1.5 * vxx_ema20_h) | (vxx_h > 40.0)
            vix_mult = vix_high.replace({True: 0.5, False: 1.0}).astype(float)

        # Relative strength multiplier.
        rs_mult = pd.Series(1.0, index=idx)
        if self._enable_rs:
            lead_spy = spy_ret_h is not None and (target_ret_h > spy_ret_h)
            lead_qqq = qqq_ret_h is not None and (target_ret_h > qqq_ret_h)
            lead_smh = smh_ret_h is not None and (target_ret_h > smh_ret_h)
            # lead_all -> 1.0, lead_spy -> 0.75, else -> 0.5
            score = pd.Series(0.5, index=idx)
            if lead_spy is not False:
                score = score.where(~lead_spy, 0.75)
            if lead_qqq is not False and lead_smh is not False:
                score = score.where(~(lead_spy & lead_qqq & lead_smh), 1.0)
            rs_mult = score

        # Volume multiplier.
        vol_mult = pd.Series(1.0, index=idx)
        if self._enable_vol:
            vol_mult = 0.7 + 0.3 * vol_surge.fillna(0).astype(float)

        # Combine: gates are 0/1, modifiers are 0.5-1.0.
        mult = (
            ma_gate.astype(float)
            * fib_gate.astype(float)
            * fib_mult
            * sox_gate.astype(float)
            * vix_mult
            * rs_mult
            * vol_mult
        )
        return mult.fillna(0.0)

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        """Generate Arete-scaled signals for target symbols."""
        base = self._base.generate(data_map)
        out: Dict[str, pd.Series] = {}

        for code in TARGET_CODES:
            df = data_map.get(code)
            if df is None or df.empty:
                continue
            sig = base.get(code)
            if sig is None or sig.empty:
                continue
            mult = self._arete_mult(code, df, data_map)
            scaled = (sig.astype(float) * mult).clip(0.0, 1.0)
            out[code] = scaled

        # Provide zero series for any remaining code so downstream callers stay aligned.
        for code, df in data_map.items():
            if code not in out:
                out[code] = pd.Series(0.0, index=df.index)

        return out
