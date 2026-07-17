"""v73_trump_beat: return-positive blend over v39b (± v39d) for Trump window.

Not a risk-off shrinker. Modes try to *add* return while holding DD:
  - agree_boost: size-up when v39d agrees with v39b
  - risk_on_scale: size-up when SPY risk score is calm
  - union_calm: fill primary flats with secondary when calm
  - pick_leader: causal rolling-perf teacher pick
  - agree_risk_on: agree boost + mild risk-on scale
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd


def _find_repo_root(anchor: Path) -> Path:
    for p in anchor.resolve().parents:
        if (p / "models" / "poc_va_macdha").exists():
            return p
    raise RuntimeError("Could not find TradingAlgoWork repo root")


def _load_module(path: Path, key: str) -> Any:
    name = f"{key}_{id(path)}"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def _load_teacher(repo_root: Path, name: str) -> Any:
    path = repo_root / "models" / "poc_va_macdha" / name / "signal_engine.py"
    if not path.exists():
        raise FileNotFoundError(name)
    return _load_module(path, f"v73_teacher_{name}").SignalEngine()


def _risk_score_spy(spy: pd.DataFrame) -> pd.Series:
    """Lightweight causal SPY risk in [0,1] (local, no shared import required)."""
    import numpy as np

    close = spy["close"].astype(float)
    peak = close.cummax()
    dd = (close / peak.replace(0, np.nan) - 1.0).fillna(0.0)
    # dd stress: -3% → 0, -10% → 1
    dd_s = ((dd - (-0.03)) / (-0.10 - (-0.03))).clip(0, 1).fillna(0.0)
    ret = close.pct_change().shift(1)
    vol = ret.rolling(20, min_periods=10).std()
    med = vol.shift(1).expanding(min_periods=20).median()
    vr = (vol / med.replace(0, np.nan)).clip(0.5, 3.0).fillna(1.0)
    vol_s = ((vr - 1.15) / (2.0 - 1.15)).clip(0, 1).fillna(0.0)
    lag = close.shift(1)
    ma = lag.rolling(50, min_periods=20).mean()
    trend_s = (lag < ma).fillna(False).astype(float)
    score = (0.5 * dd_s + 0.35 * vol_s + 0.15 * trend_s).clip(0, 1)
    return score.rename("risk_score")


class SignalEngine:
    def __init__(self) -> None:
        self_dir = Path(__file__).resolve().parent
        repo_root = _find_repo_root(self_dir)
        self._blend = _load_module(self_dir / "blend.py", "v73_blend")

        hunt_path = self_dir / "hunt_config.json"
        self._hunt: Dict[str, Any] = {
            "mode": "agree_risk_on",
            "primary": "v39b_live_adapt",
            "secondary": "v39d_confluence",
            "boost": 1.18,
            "max_boost": 0.18,
            "max_scale": 1.40,
            "calm_threshold": 0.35,
            "secondary_scale": 0.90,
            "lookback": 40,
            "risk_floor": 0.0,
        }
        if hunt_path.exists():
            try:
                self._hunt.update(json.loads(hunt_path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                pass

        self._primary_name = str(self._hunt.get("primary", "v39b_live_adapt"))
        sec = self._hunt.get("secondary")
        self._secondary_name: Optional[str] = str(sec) if sec else None
        self._mode = str(self._hunt.get("mode", "agree_risk_on"))

        self._primary = _load_teacher(repo_root, self._primary_name)
        self._secondary = None
        if self._secondary_name:
            try:
                self._secondary = _load_teacher(repo_root, self._secondary_name)
            except Exception as exc:
                print(f"[v73] secondary load failed: {exc}")

        self.last_risk_score: Optional[pd.Series] = None

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        primary_sigs = self._primary.generate(data_map)
        secondary_sigs: Dict[str, pd.Series] = {}
        if self._secondary is not None:
            try:
                secondary_sigs = self._secondary.generate(data_map)
            except Exception as exc:
                print(f"[v73] secondary generate failed: {exc}")

        spy = data_map.get("SPY.US")
        risk = None
        if spy is not None and not spy.empty and "close" in spy.columns:
            risk = _risk_score_spy(spy)
            self.last_risk_score = risk

        params = {
            "boost": self._hunt.get("boost", 1.18),
            "max_boost": self._hunt.get("max_boost", 0.18),
            "max_scale": self._hunt.get("max_scale", 1.40),
            "calm_threshold": self._hunt.get("calm_threshold", 0.35),
            "secondary_scale": self._hunt.get("secondary_scale", 0.90),
            "lookback": self._hunt.get("lookback", 40),
            "risk_floor": self._hunt.get("risk_floor", 0.0),
            "entry_thresh": self._hunt.get("entry_thresh", 0.5),
            "elevated_threshold": self._hunt.get("elevated_threshold", 0.55),
            "elevated_mult": self._hunt.get("elevated_mult", 0.85),
            "high_beta_codes": self._hunt.get(
                "high_beta_codes", ["IONQ.US", "APLD.US", "TSLA.US"]
            ),
            "high_beta_base": self._hunt.get("high_beta_base", 0.92),
            "high_beta_elevated": self._hunt.get("high_beta_elevated", 0.55),
            "core_elevated": self._hunt.get("core_elevated", 0.90),
            "position_cap": self._hunt.get("position_cap", 0.50),
            "target_vol": self._hunt.get("target_vol", 0.014),
            "vol_floor": self._hunt.get("vol_floor", 0.004),
            "min_mult": self._hunt.get("min_mult", 0.50),
            "max_mult": self._hunt.get("max_mult", 1.15),
            "dd_soft": self._hunt.get("dd_soft", -0.05),
            "dd_hard": self._hunt.get("dd_hard", -0.14),
            "dd_min_mult": self._hunt.get("dd_min_mult", 0.40),
            "use_inv_vol": self._hunt.get("use_inv_vol", True),
            "use_name_dd": self._hunt.get("use_name_dd", True),
            "use_agree": self._hunt.get("use_agree", True),
            "symbol_scales": self._hunt.get("symbol_scales", {}),
            "symbol_caps": self._hunt.get("symbol_caps", {}),
            "default_symbol_scale": self._hunt.get("default_symbol_scale", 1.0),
            "default_symbol_cap": self._hunt.get("default_symbol_cap"),
        }

        out: Dict[str, pd.Series] = {}
        for code, df in data_map.items():
            p = primary_sigs.get(code)
            if p is None or (hasattr(p, "empty") and p.empty):
                out[code] = pd.Series(0.0, index=df.index if df is not None else [])
                continue
            p = p.reindex(df.index).fillna(0.0).astype(float)
            s = secondary_sigs.get(code)
            if s is not None:
                s = s.reindex(df.index).fillna(0.0).astype(float)
            r = risk.reindex(df.index).ffill().fillna(0.0) if risk is not None else None
            close = df["close"] if df is not None and "close" in df.columns else None
            out[code] = self._blend.blend_signals(
                self._mode,
                p,
                secondary=s,
                risk_score=r,
                close=close,
                params=params,
                code=code,
            )
        return out
