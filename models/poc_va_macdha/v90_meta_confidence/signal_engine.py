"""v90_meta_confidence: two-sided meta-labeling engine with calibrated confidence.

Design (see docs/MODEL_REVIEW_AND_HIGH_WINRATE_PLAN.md and MODEL.md):
  - Causal features (features.py) -> two XGBoost meta-labelers (LONG / SHORT
    heads) trained on triple-barrier labels via purged K-fold.
  - Raw score drives the BUY / SELL / FLAT decision (continuous, monotonic);
    the isotonic-calibrated probability is the honest confidence shown to the
    operator.
  - Emits SIGNED target weights: positive = BUY (long), negative = SELL (short)
    when ``allow_short`` is enabled, else the short head becomes a flatten/avoid
    signal only. FLAT = 0.

Fail-closed: if any artifact (booster / calibration / thresholds) is missing or
xgboost is unavailable, the engine returns FLAT everywhere with zero confidence.
It never fabricates a signal.

Artifacts are produced by tools/train_v90_meta_confidence.py:
  meta_xgb_long.json, meta_xgb_short.json, calibration.json, thresholds.json.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd


def _load_features_module():
    here = Path(__file__).resolve().parent
    path = here / "features.py"
    module_name = f"v90_features_{id(path)}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


class _Calibrator:
    """Isotonic (piecewise-linear) or identity map, restored from JSON."""

    def __init__(self, art: Dict[str, object]) -> None:
        self._kind = str(art.get("type", "identity"))
        if self._kind == "isotonic":
            self._x = np.asarray(art["x"], dtype=float)
            self._y = np.asarray(art["y"], dtype=float)
        else:
            self._x = np.asarray([0.0, 1.0], dtype=float)
            self._y = np.asarray([0.0, 1.0], dtype=float)

    def apply(self, p: np.ndarray) -> np.ndarray:
        if self._kind == "isotonic":
            return np.interp(p, self._x, self._y)
        return p


class SignalEngine:
    """Two-sided calibrated meta-labeler. Long/flat by default; short-enabled
    via hunt_config.allow_short."""

    def __init__(self) -> None:
        self._dir = Path(__file__).resolve().parent
        self._feat = _load_features_module()
        self.last_confidence: Dict[str, pd.Series] = {}
        self.last_side: Dict[str, pd.Series] = {}
        self._ready = False

        hunt = self._load_json(self._dir / "hunt_config.json") or {}
        self._allow_short: bool = bool(hunt.get("allow_short", True))
        self._base_scale: float = float(hunt.get("base_scale", 0.25))
        self._selective_scale: float = float(hunt.get("selective_scale", 0.35))

        thr = self._load_json(self._dir / "thresholds.json") or {}
        self._enter_hi: float = float(thr.get("enter_hi", 0.67))
        self._enter_lo: float = float(thr.get("enter_lo", 0.63))
        self._selective: float = float(thr.get("selective", 0.72))

        self._long_model = self._load_booster("meta_xgb_long.json")
        self._short_model = self._load_booster("meta_xgb_short.json")
        cal = self._load_json(self._dir / "calibration.json") or {}
        self._cal_long = _Calibrator(cal.get("long", {"type": "identity"}))
        self._cal_short = _Calibrator(cal.get("short", {"type": "identity"}))
        self._ready = self._long_model is not None and self._short_model is not None

    @staticmethod
    def _load_json(path: Path) -> Optional[Dict[str, object]]:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def _load_booster(self, name: str):
        path = self._dir / name
        if not path.exists():
            return None
        try:
            import xgboost as xgb
        except ImportError:
            return None
        booster = xgb.Booster()
        booster.load_model(str(path))
        return booster

    def _predict(self, booster, feats: pd.DataFrame) -> np.ndarray:
        import xgboost as xgb

        dm = xgb.DMatrix(feats.to_numpy(dtype=float), feature_names=list(feats.columns))
        return np.asarray(booster.predict(dm), dtype=float)

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        out: Dict[str, pd.Series] = {}
        self.last_confidence = {}
        self.last_side = {}
        for code, df in data_map.items():
            if df is None or df.empty:
                out[code] = pd.Series(0.0, index=(df.index if df is not None else pd.DatetimeIndex([])))
                continue
            idx = df.index
            target = pd.Series(0.0, index=idx)
            conf = pd.Series(0.0, index=idx)
            side = pd.Series("FLAT", index=idx)
            if not self._ready:
                out[code] = target
                self.last_confidence[code] = conf
                self.last_side[code] = side
                continue

            feats = self._feat.build_features(df)
            valid = feats.notna().all(axis=1)
            fv = feats[valid]
            if fv.empty:
                out[code] = target
                self.last_confidence[code] = conf
                self.last_side[code] = side
                continue

            raw_long = self._predict(self._long_model, fv)
            raw_short = self._predict(self._short_model, fv)
            cal_long = self._cal_long.apply(raw_long)
            cal_short = self._cal_short.apply(raw_short)

            pos = np.where(valid.to_numpy())[0]
            for k, row in enumerate(pos):
                rl, rs = raw_long[k], raw_short[k]
                cl, cs = cal_long[k], cal_short[k]
                long_ok = rl >= self._enter_lo
                short_ok = rs >= self._enter_lo
                if long_ok and rl >= rs:
                    scale = self._selective_scale if rl >= self._selective else self._base_scale
                    target.iloc[row] = scale
                    conf.iloc[row] = cl
                    side.iloc[row] = "BUY"
                elif short_ok:
                    scale = self._selective_scale if rs >= self._selective else self._base_scale
                    target.iloc[row] = -scale if self._allow_short else 0.0
                    conf.iloc[row] = cs
                    side.iloc[row] = "SELL" if self._allow_short else "SELL_FLATTEN"

            out[code] = target
            self.last_confidence[code] = conf
            self.last_side[code] = side
        return out
