"""v25_regime_grow — equity SIDE = v23_devin_overlay + portfolio risk throttle.

Primary side rules are frozen in the WINNER parent. This engine only applies
risk-regime scaling so the stock sleeve can act as the "hedge until options"
book in backtests and on the trade desk.

Live vehicle choice (options attack vs equity hedge) is in tools/risk_manager.py.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_PARENT = _HERE.parent / "v23_devin_overlay" / "signal_engine.py"
_POLICY = _HERE / "RISK_POLICY.json"


def _load_parent():
    if not _PARENT.exists():
        raise FileNotFoundError(f"v23 parent engine missing: {_PARENT}")
    spec = importlib.util.spec_from_file_location("v23_devin_overlay_se", _PARENT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod.SignalEngine()


def _load_policy() -> dict:
    if _POLICY.exists():
        return json.loads(_POLICY.read_text())
    return {
        "drawdown": {"soft_throttle": 0.08, "halt_new": 0.18, "flatten": 0.28},
        "equity": {"kelly_fraction": 0.5},
    }


def _daily_close(df: pd.DataFrame) -> pd.Series:
    d = df.copy()
    d.index = pd.to_datetime(d.index)
    if getattr(d.index, "tz", None) is not None:
        d.index = d.index.tz_localize(None)
    return d["close"].resample("1D").last().dropna().astype(float)


def _xlp_spy_defensive(xlp_df: pd.DataFrame, spy_df: pd.DataFrame) -> pd.Series:
    """True when defensive (same DNA as v20b/v23)."""
    xlp = _daily_close(xlp_df)
    spy = _daily_close(spy_df)
    idx = xlp.index.intersection(spy.index)
    ratio = xlp.reindex(idx) / spy.reindex(idx)
    ma20 = ratio.rolling(20, min_periods=20).mean()
    ma50 = ratio.rolling(50, min_periods=50).mean()
    defensive = (ratio > ma20) & (ma20 > ma50)
    return defensive.astype(bool).shift(1).fillna(False)


class SignalEngine:
    """Wraps v23; scales sizes for equity-hedge risk posture."""

    def __init__(self):
        self.parent = _load_parent()
        self.policy = _load_policy()
        # mild equity risk lean vs full v23 size (hedge sleeve, not max aggression)
        eq = self.policy.get("equity", {})
        self.equity_size_cap = float(eq.get("kelly_fraction", 0.5)) / 0.5  # 1.0 at half-Kelly DNA
        self.equity_size_cap = float(np.clip(self.equity_size_cap, 0.5, 1.0))
        # optional global clip so hedge book is slightly smaller than pure attack equity
        self.hedge_scale = 0.85

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        raw = self.parent.generate(data_map)
        # Extra defensive flatten on XLP/SPY if parent already gated — keep consistent
        spy_df = data_map.get("SPY.US")
        xlp_df = data_map.get("XLP.US")
        defensive = None
        if spy_df is not None and xlp_df is not None and not xlp_df.empty and not spy_df.empty:
            defensive = _xlp_spy_defensive(xlp_df, spy_df)

        out: Dict[str, pd.Series] = {}
        for code, sig in raw.items():
            s = sig.astype(float) * self.hedge_scale
            # clip positive sizes; never invent shorts here
            s = s.clip(lower=0.0, upper=self.equity_size_cap)
            if defensive is not None and not s.empty:
                idx = pd.to_datetime(s.index)
                if getattr(idx, "tz", None) is not None:
                    idx = idx.tz_localize(None)
                days = idx.normalize()
                d = defensive.reindex(days).ffill().fillna(False)
                d.index = s.index
                s = s.where(~d.astype(bool), 0.0)
            out[code] = s.astype(float)
        return out
