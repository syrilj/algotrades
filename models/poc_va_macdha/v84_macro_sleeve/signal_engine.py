"""v84_macro_sleeve: v72 dual-sleeve with a global SPY macro soft-size overlay.

Design (pre-registered, anti-blend)
-----------------------------------
Naive per-symbol regime scaling (v83) underperformed v72. v84 uses the same
institutional_flow features but on SPY as a global macro proxy, then applies a
single soft-size multiplier to every v72 target weight:

1. **Base signal** — run frozen `v72_dual_sleeve` unchanged.
2. **Macro state** — compute SPY trend/vol/RSI from `compute_features`.
3. **Soft-size** — scale all target weights by the pre-registered macro matrix.
4. **Portfolio cap** — per-symbol target weight ≤ `max_weight`.

This is a global overlay, not per-symbol filtering, so v72's stock selection is
preserved and only aggregate risk is modulated.
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


def _load_base_engine(repo_root: Path, model_name: str) -> Any:
    path = repo_root / "models" / "poc_va_macdha" / model_name / "signal_engine.py"
    if not path.exists():
        raise FileNotFoundError(f"Base engine {model_name} not found at {path}")
    module_name = f"v84_base_{model_name.replace('.', '_')}_{id(path)}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod.SignalEngine()


def _load_hunt(self_dir: Path) -> Dict[str, Any]:
    defaults = {
        "base_model": "v72_dual_sleeve",
        "macro_proxy_symbol": "SPY.US",
        "macro_floor": 0.2,
        "macro_cap": 1.0,
        "trend_low_vol_scale": 1.0,
        "trend_high_vol_scale": 0.7,
        "chop_low_vol_scale": 0.5,
        "chop_high_vol_scale": 0.2,
        "max_weight": 0.5,
    }
    hunt_path = self_dir / "hunt_config.json"
    if hunt_path.exists():
        try:
            overrides = json.loads(hunt_path.read_text(encoding="utf-8"))
            if isinstance(overrides, dict):
                defaults.update(overrides)
        except json.JSONDecodeError:
            pass
    return defaults


class SignalEngine:
    """v72 dual-sleeve with a global SPY macro soft-size overlay."""

    def __init__(self) -> None:
        self_dir = Path(__file__).resolve().parent
        repo_root = _find_repo_root(self_dir)
        self._hunt = _load_hunt(self_dir)

        tools_path = str(repo_root / "tools")
        if tools_path not in sys.path:
            sys.path.insert(0, tools_path)

        self._base_model = str(self._hunt.get("base_model", "v72_dual_sleeve"))
        self._macro_symbol = str(self._hunt.get("macro_proxy_symbol", "SPY.US"))
        self._floor = float(self._hunt.get("macro_floor", 0.2))
        self._cap = float(self._hunt.get("macro_cap", 1.0))
        self._trend_low_vol = float(self._hunt.get("trend_low_vol_scale", 1.0))
        self._trend_high_vol = float(self._hunt.get("trend_high_vol_scale", 0.7))
        self._chop_low_vol = float(self._hunt.get("chop_low_vol_scale", 0.5))
        self._chop_high_vol = float(self._hunt.get("chop_high_vol_scale", 0.2))
        self._max_weight = float(self._hunt.get("max_weight", 0.5))

        self.last_confidence: Dict[str, pd.Series] = {}
        self.last_sleeve: Dict[str, pd.Series] = {}

        self._base: Optional[Any] = None
        try:
            self._base = _load_base_engine(repo_root, self._base_model)
        except Exception as exc:
            print(f"[v84] warning: base {self._base_model} failed: {exc}")

    def _macro_scale(self, spy_df: pd.DataFrame) -> pd.Series:
        from institutional_flow.features import compute_features

        required = ("open", "high", "low", "close", "volume")
        if not all(c in spy_df.columns for c in required):
            return pd.Series(1.0, index=spy_df.index)

        feats = compute_features(spy_df)
        idx = spy_df.index
        trend = feats["trend"].reindex(idx).fillna(0.0).astype(float)
        vol_regime = feats["vol_regime"].reindex(idx).fillna(0.0).astype(float)

        scale = pd.Series(1.0, index=idx)
        scale.where(~((trend > 0.5) & (vol_regime < 0.5)), self._trend_low_vol, inplace=True)
        scale.where(~((trend > 0.5) & (vol_regime > 0.5)), self._trend_high_vol, inplace=True)
        scale.where(~((trend <= 0.5) & (vol_regime < 0.5)), self._chop_low_vol, inplace=True)
        scale.where(~((trend <= 0.5) & (vol_regime > 0.5)), self._chop_high_vol, inplace=True)
        return scale.clip(self._floor, self._cap)

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        if self._base is None:
            return {code: pd.Series(0.0, index=df.index) for code, df in data_map.items()}

        base_sigs = self._base.generate(data_map)
        base_conf = getattr(self._base, "last_confidence", None) or {}
        self.last_confidence = base_conf if isinstance(base_conf, dict) else {}
        self.last_sleeve = getattr(self._base, "last_sleeve", {}) or {}

        spy_df = data_map.get(self._macro_symbol)
        if spy_df is None or spy_df.empty:
            return base_sigs

        macro_scale = self._macro_scale(spy_df)

        out: Dict[str, pd.Series] = {}
        for code, df in data_map.items():
            sig = base_sigs.get(code)
            if sig is None or sig.empty:
                out[code] = pd.Series(0.0, index=df.index)
                continue
            scaled = (sig.reindex(df.index).fillna(0.0) * macro_scale.reindex(df.index).fillna(1.0)).clip(upper=self._max_weight)
            out[code] = scaled.astype(float)
        return out
