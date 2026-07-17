"""v61_institutional_flow: pilot signal engine using the reusable
`tools.institutional_flow` feature module.

This is a thin SignalEngine wrapper that demonstrates the new OHLCV-safe
institutional-flow feature set in the standard backtester.  It is intentionally
kept as a heuristic pilot, not a trained XGB model.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd


def _find_repo_root(anchor: Path) -> Path:
    """Locate the repo root by searching for the new feature module."""
    for p in anchor.resolve().parents:
        if (p / "tools" / "institutional_flow" / "features.py").exists():
            return p
    raise RuntimeError("Could not locate tools/institutional_flow/features.py")


def _load_features_module(repo_root: Path) -> Any:
    """Import tools/institutional_flow/features.py as a standalone module.

    The runner forbids top-level executable statements, so module loading is
    done inside the SignalEngine constructor.  features.py only needs numpy and
    pandas; its internal __init__ imports are not used.
    """
    features_path = repo_root / "tools" / "institutional_flow" / "features.py"
    spec = importlib.util.spec_from_file_location("institutional_flow_features", str(features_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _heuristic_proba(features: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """High-conviction pullback-to-VWAP + institutional-absorption score.

    Adapted from the v60 heuristic; the inputs are the same columns produced by
    `tools.institutional_flow.compute_features`.
    """
    trend = features["trend"]
    above_vwap = features["above_vwap"]
    ofi = features["ofi"]
    ofi_persistence = features["ofi_persistence"]
    absorption = features["absorption"].clip(-50.0, 50.0) / 10.0
    rsi = features["rsi"].fillna(50.0)
    vol_regime = features["vol_regime"]
    dist_vwap = features["dist_vwap_pct"]
    range_pct = features["range_pct"]
    atr_pct = features["atr_pct"]
    vol_z = features["vol_z"].clip(-5.0, 5.0)
    schedule_dev = features["schedule_dev"].clip(-2.0, 2.0)
    vpin = features["vpin"].clip(0.0, 1.0)

    vwap_pullback = ((dist_vwap >= 0.0) & (dist_vwap <= 0.015)).astype(float)
    not_extended = (dist_vwap < 0.03).astype(float)

    # Range compression: current bar range is tight relative to its ATR
    compression = (range_pct < atr_pct * 0.8).astype(float)

    ofi_ok = (ofi > 0.0).astype(float)
    ofi_persistent = (ofi_persistence > 0.0).astype(float)

    # Stealth volume: not a climax, but not dead either
    vol_stealth = ((vol_z > -0.5) & (vol_z < 1.0)).astype(float)

    # RSI healthy: not overbought, not deeply oversold
    rsi_ok = ((rsi > 45.0) & (rsi < 70.0)).astype(float)

    absorption_ok = (absorption > 0.5).astype(float)

    vol_regime_ok = (vol_regime == 0.0).astype(float)
    schedule_ok = (schedule_dev.abs() < 1.0).astype(float)

    score = (
        3.0 * trend
        + 2.5 * vwap_pullback
        + 1.0 * not_extended
        + 1.5 * compression
        + 1.5 * ofi_ok
        + 1.0 * ofi_persistent
        + 1.0 * vol_stealth
        + 1.0 * rsi_ok
        + 0.5 * absorption_ok
        + 0.5 * vol_regime_ok
        + 0.5 * schedule_ok
        + 0.2 * vpin
        - 3.0 * (dist_vwap < 0.0).astype(float)
        - 2.0 * (rsi >= 70.0).astype(float)
    )

    temperature = float(params.get("temperature", 0.5))
    proba = (1.0 / (1.0 + np.exp(-score * temperature))).clip(0.0, 1.0)
    return proba


class SignalEngine:
    """Pilot microstructure engine backed by `tools.institutional_flow`."""

    def __init__(self) -> None:
        self_dir = Path(__file__).resolve().parent
        repo_root = _find_repo_root(self_dir)
        self._features = _load_features_module(repo_root)

        self._hunt: Dict[str, Any] = {}
        hunt_path = self_dir / "hunt_config.json"
        if hunt_path.exists():
            self._hunt = json.loads(hunt_path.read_text(encoding="utf-8"))

        self._params = self._make_params()

    def _make_params(self) -> Dict[str, Any]:
        defaults = {
            "ofi_short": 20,
            "ofi_long": 50,
            "absorption_lookback": 20,
            "vol_look": 20,
            "trend_len": 200,
            "vol_len": 50,
            "schedule_lookback": 30,
            "vpin_bucket_frac": 0.05,
            "vpin_n_buckets": 20,
            "max_hold_bars": 20,
            "sl_atr_mult": 1.5,
            "tp_atr_mult": 3.0,
            "min_conviction": 0.70,
            "signal_scale": 1.0,
            "temperature": 0.5,
            "rsi_max": 70.0,
            "require_above_vwap": True,
            "require_trend": True,
        }
        merged = {**defaults, **self._hunt}
        return merged

    def _compute_features(self, df: pd.DataFrame) -> pd.DataFrame:
        return self._features.compute_features(df, self._params)

    def _exit_signal(self, df: pd.DataFrame, features: pd.DataFrame, state: Dict[str, Any], i: int) -> bool:
        close = df["close"].astype(float).values
        entry_price = float(state["entry_price"])
        bars = int(state["bars_in_pos"])

        atr_pct = float(features["atr_pct"].iloc[i])
        sl_mult = float(self._params["sl_atr_mult"])
        tp_mult = float(self._params["tp_atr_mult"])
        sl_pct = max(0.005, sl_mult * atr_pct)
        tp_pct = max(0.010, tp_mult * atr_pct)
        if close[i] < entry_price * (1.0 - sl_pct):
            return True
        if close[i] > entry_price * (1.0 + tp_pct):
            return True

        if bars >= int(self._params["max_hold_bars"]):
            return True

        if bool(self._params["require_trend"]) and features["trend"].iloc[i] == 0.0:
            return True
        if bool(self._params["require_above_vwap"]) and features["above_vwap"].iloc[i] == 0.0:
            return True

        return False

    def _generate_one(self, df: pd.DataFrame) -> pd.Series:
        features = self._compute_features(df)
        proba = _heuristic_proba(features, self._params)
        close = df["close"].astype(float)
        idx = df.index
        out = pd.Series(0.0, index=idx)

        in_pos = False
        entry_price = 0.0
        bars_in_pos = 0
        min_conviction = float(self._params["min_conviction"])
        rsi_max = float(self._params["rsi_max"])
        require_trend = bool(self._params["require_trend"])
        require_above_vwap = bool(self._params["require_above_vwap"])

        for i in range(len(idx)):
            p = float(proba.iloc[i])
            rsi = float(features["rsi"].iloc[i])
            trend_ok = (not require_trend) or features["trend"].iloc[i] > 0.5
            vwap_ok = (not require_above_vwap) or features["above_vwap"].iloc[i] > 0.5
            rsi_ok = rsi < rsi_max

            if not in_pos:
                if p >= min_conviction and trend_ok and vwap_ok and rsi_ok:
                    in_pos = True
                    entry_price = float(close.iloc[i])
                    bars_in_pos = 0
            else:
                state = {"entry_price": entry_price, "bars_in_pos": bars_in_pos}
                if self._exit_signal(df, features, state, i):
                    in_pos = False
                else:
                    bars_in_pos += 1

            out.iloc[i] = float(self._params["signal_scale"]) if in_pos else 0.0

        return out

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        out: Dict[str, pd.Series] = {}
        for code, df in data_map.items():
            if df is None or df.empty:
                out[code] = pd.Series(0.0, index=pd.DatetimeIndex([], dtype="datetime64[ns]"))
                continue
            out[code] = self._generate_one(df)
        return out
