"""v51_vpa_reflexivity: VPA + reflexivity XGB meta-labeler as a desk engine.

Uses features.py + meta_xgb_final.json. Produces a target weight series for the
standard backtester / trade-desk generate() path.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

try:
    from xgboost import XGBClassifier
except Exception:  # noqa: BLE001
    XGBClassifier = None  # type: ignore[misc, assignment]


def _load_features_module(model_dir: Path) -> Any:
    path = model_dir / "features.py"
    spec = importlib.util.spec_from_file_location(
        f"v51_features_{id(path)}", str(path)
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


class SignalEngine:
    """Long-only meta model on VPA / reflexivity primary events."""

    def __init__(self) -> None:
        self_dir = Path(__file__).resolve().parent
        self._features = _load_features_module(self_dir)

        meta_path = self_dir / "meta_config.json"
        self._meta: Dict[str, Any] = {}
        if meta_path.exists():
            self._meta = json.loads(meta_path.read_text(encoding="utf-8"))

        hunt_path = self_dir / "hunt_config.json"
        self._hunt: Dict[str, Any] = {}
        if hunt_path.exists():
            self._hunt = json.loads(hunt_path.read_text(encoding="utf-8"))

        self._feat_cols: List[str] = list(self._meta.get("feat_cols", []))
        self._threshold = float(
            self._hunt.get("threshold", self._meta.get("threshold", 0.55))
        )
        self._signal_scale = float(self._hunt.get("signal_scale", 1.0))
        self._max_hold = int(self._hunt.get("max_hold", self._meta.get("max_hold", 5)))

        self._booster: Optional[Any] = None
        if XGBClassifier is not None:
            xgb_path = self_dir / "meta_xgb_final.json"
            if xgb_path.exists():
                try:
                    self._booster = XGBClassifier()
                    self._booster.load_model(str(xgb_path))
                except Exception as exc:  # noqa: BLE001
                    print(f"[v51] warning: could not load XGB: {exc}")
                    self._booster = None

    def _proba(self, features: pd.DataFrame) -> pd.Series:
        if self._booster is None or not self._feat_cols:
            # Heuristic fallback if XGB missing
            base = features.get("volume_price_confirm", pd.Series(0.0, index=features.index))
            trend = features.get("above_sma50", pd.Series(0.0, index=features.index))
            vwap = features.get("above_vwap", pd.Series(0.0, index=features.index))
            raw = 0.5 + 0.15 * base.clip(-2, 2) + 0.1 * trend + 0.1 * vwap
            return raw.clip(0.0, 1.0)

        cols = [c for c in self._feat_cols if c in features.columns]
        X = features[cols].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        # Align column count if model expects exact order
        for c in self._feat_cols:
            if c not in X.columns:
                X[c] = 0.0
        X = X[self._feat_cols]
        try:
            p = self._booster.predict_proba(X)[:, 1]
        except Exception:
            p = self._booster.predict(X)
            p = np.asarray(p, dtype=float)
        return pd.Series(p, index=features.index)

    def _generate_one(self, df: pd.DataFrame, spy_df: Optional[pd.DataFrame] = None) -> pd.Series:
        features = self._features.compute_features(df, spy_df=spy_df)
        try:
            events = self._features.primary_events(features)
        except Exception:  # noqa: BLE001
            events = pd.Series(True, index=features.index)

        proba = self._proba(features)
        idx = df.index
        out = pd.Series(0.0, index=idx)
        in_pos = False
        bars = 0
        thr = self._threshold
        scale = self._signal_scale
        max_hold = self._max_hold

        for i in range(len(idx)):
            p = float(proba.iloc[i]) if i < len(proba) else 0.0
            ev = bool(events.iloc[i]) if i < len(events) else True
            if not in_pos:
                if ev and p >= thr:
                    in_pos = True
                    bars = 0
            else:
                bars += 1
                if bars >= max_hold or p < thr * 0.85:
                    in_pos = False
            out.iloc[i] = scale if in_pos else 0.0
        return out

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        spy = None
        for key in ("SPY.US", "SPY", "spy"):
            if key in data_map and data_map[key] is not None and not data_map[key].empty:
                spy = data_map[key]
                break

        out: Dict[str, pd.Series] = {}
        for code, df in data_map.items():
            if df is None or df.empty:
                out[code] = pd.Series(0.0, index=pd.DatetimeIndex([]))
                continue
            if str(code).upper().startswith("SPY"):
                # Don't self-trade SPY as a reflexivity long in isolation
                out[code] = pd.Series(0.0, index=df.index)
                continue
            out[code] = self._generate_one(df, spy_df=spy)
        return out
