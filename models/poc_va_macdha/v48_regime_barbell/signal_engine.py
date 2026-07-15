"""v48_regime_barbell: causal blend of independent trend and mean-reversion sleeves."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd


STATIC_POLICIES = {
    "static_80_20": (0.80, 0.20),
    "static_75_25": (0.75, 0.25),
    "static_67_33": (0.67, 0.33),
}
REGIME_WEIGHTS = {
    "risk_on": (0.90, 0.10),
    "neutral": (0.70, 0.30),
    "risk_off": (0.25, 0.75),
}


def _load_teachers():
    here = Path(__file__).resolve().parent
    candidates = [here / "v48_teachers.py", here.parent / "_shared" / "v48_teachers.py"]
    for path in candidates:
        if path.exists():
            spec = importlib.util.spec_from_file_location("v48_teachers", path)
            module = importlib.util.module_from_spec(spec)
            assert spec and spec.loader
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            return module
    raise FileNotFoundError("v48_teachers.py is not bundled with this model")


def _load_config() -> dict:
    here = Path(__file__).resolve().parent
    candidates = [here.parent / "config.json", here / "config.json"]
    for path in candidates:
        if path.exists():
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                continue
    return {}


def _feedback_weight(
    trend: pd.Series, mean_reversion: pd.Series, close: pd.Series, base: pd.Series
) -> pd.Series:
    ret = close.pct_change().fillna(0.0)
    trend_ret = trend.shift(1).fillna(0.0) * ret
    mean_ret = mean_reversion.shift(1).fillna(0.0) * ret
    trend_ewma = trend_ret.ewm(span=60, adjust=False, min_periods=60).mean().shift(1)
    mean_ewma = mean_ret.ewm(span=60, adjust=False, min_periods=60).mean().shift(1)
    denominator = (
        trend_ret.abs().ewm(span=60, adjust=False, min_periods=60).mean().shift(1)
        + mean_ret.abs().ewm(span=60, adjust=False, min_periods=60).mean().shift(1)
    )
    relative = ((trend_ewma - mean_ewma) / denominator.replace(0.0, np.nan)).clip(-1.0, 1.0)
    return (base + 0.10 * relative.fillna(0.0)).clip(0.10, 0.90)


class SignalEngine:
    def __init__(self) -> None:
        cfg = _load_config()
        v48 = cfg.get("v48", {}) if isinstance(cfg.get("v48"), dict) else {}
        self.policy = str(v48.get("policy", "static_75_25"))
        self.strict_regime = bool(v48.get("strict_regime", False))
        self.regime_path = v48.get("regime_path")
        self.last_health: dict[str, object] = {"mode": "initialising", "fallback": False}
        teachers = _load_teachers()
        self._trend = teachers.TrendTeacher()
        self._mean_reversion = teachers.MeanReversionTeacher()

    def _regime_labels(self, index: pd.DatetimeIndex) -> pd.Series:
        path = Path(self.regime_path) if self.regime_path else Path(__file__).resolve().parents[1] / "_shared" / "regime" / "regime_daily.parquet"
        if not path.exists():
            if self.strict_regime:
                raise FileNotFoundError(f"missing causal regime data: {path}")
            self.last_health = {"mode": "degraded_static", "fallback": True, "reason": "missing_regime"}
            return pd.Series("neutral", index=index)
        regime = pd.read_parquet(path)
        regime.index = pd.to_datetime(regime.index)
        if getattr(regime.index, "tz", None) is not None:
            regime.index = regime.index.tz_convert("America/New_York").tz_localize(None)
        if "label" not in regime:
            raise ValueError("regime parquet has no label column")
        # At every intraday timestamp, use a regime row from the preceding session.
        lookup = pd.DatetimeIndex(index).normalize() - pd.Timedelta(days=1)
        labels = regime["label"].reindex(lookup, method="ffill")
        labels.index = index
        if labels.isna().any():
            if self.strict_regime:
                raise ValueError("regime coverage is incomplete")
            labels = labels.fillna("neutral")
            self.last_health = {"mode": "degraded_static", "fallback": True, "reason": "incomplete_regime"}
        else:
            self.last_health = {"mode": "causal_regime", "fallback": False}
        return labels.astype(str)

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        trend = self._trend.generate(data_map)
        mean_reversion = self._mean_reversion.generate(data_map)
        out: Dict[str, pd.Series] = {}
        for code, frame in data_map.items():
            index = trend[code].index
            if self.policy in STATIC_POLICIES:
                trend_weight = pd.Series(STATIC_POLICIES[self.policy][0], index=index)
            else:
                labels = self._regime_labels(index)
                trend_weight = labels.map(lambda label: REGIME_WEIGHTS.get(label, REGIME_WEIGHTS["neutral"])[0]).astype(float)
                if self.policy == "regime_feedback":
                    close = frame["close"].reindex(index).astype(float)
                    trend_weight = _feedback_weight(trend[code], mean_reversion[code], close, trend_weight)
                elif self.policy != "regime":
                    raise ValueError(f"unknown v48 policy: {self.policy}")
            mean_weight = 1.0 - trend_weight
            out[code] = (trend_weight * trend[code] + mean_weight * mean_reversion[code]).clip(0.0, 1.0).astype(float)
        return out
