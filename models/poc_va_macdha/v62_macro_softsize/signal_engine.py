"""v62_macro_softsize: soft size-down overlay on frozen v39d_confluence.

No hard entry blocks. Multiplies v39d target positions by a regime size
multiplier in [size_floor, 1.0] derived from SPY realized vol / trend.
Missing SPY → identity mult (campaign should still score; if no variation,
harness can fail as identity).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
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
    module_name = f"base_{model_name.replace('.', '_')}_{id(path)}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[arg-type]
    return mod.SignalEngine()


def _regime_size_mult(spy: pd.DataFrame, size_floor: float = 0.25) -> pd.Series:
    """Point-in-time soft size mult from SPY vol and trend (lagged).

    - High realized vol → size down
    - Below slow MA → size down
    Multiplier in [size_floor, 1.0], never blocks entries to zero via hard gate
    (floor keeps optional residual size; floor can be 0.25).
    """
    close = spy["close"].astype(float)
    ret = close.pct_change()
    # lag returns before rolling (causal)
    vol = ret.shift(1).rolling(20, min_periods=10).std()
    vol_med = vol.expanding(min_periods=20).median()
    ma = close.shift(1).rolling(50, min_periods=20).mean()
    # vol ratio > 1 → hostile
    vol_ratio = (vol / vol_med.replace(0, np.nan)).clip(0.5, 2.5).fillna(1.0)
    # map vol_ratio 1→1.0, 2→size_floor
    vol_mult = 1.0 - (vol_ratio - 1.0).clip(0, 1.0) * (1.0 - size_floor)
    trend_ok = (close.shift(1) >= ma).fillna(True)
    trend_mult = pd.Series(np.where(trend_ok, 1.0, 0.5 + 0.5 * size_floor), index=close.index)
    mult = (vol_mult * trend_mult).clip(size_floor, 1.0)
    return mult.astype(float)


class SignalEngine:
    def __init__(self) -> None:
        self_dir = Path(__file__).resolve().parent
        repo_root = _find_repo_root(self_dir)
        hunt_path = self_dir / "hunt_config.json"
        self._hunt = json.loads(hunt_path.read_text(encoding="utf-8")) if hunt_path.exists() else {}
        self._size_floor = float(self._hunt.get("size_floor", 0.25))
        self._base = _load_base_engine(repo_root, "v39d_confluence")

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        base_sigs = self._base.generate(data_map)
        spy = data_map.get("SPY.US")
        if spy is None or spy.empty or "close" not in spy.columns:
            # Clean degradation: identity (no soft size). Campaign may still run.
            return base_sigs
        mult = _regime_size_mult(spy, size_floor=self._size_floor)
        out: Dict[str, pd.Series] = {}
        for code, sig in base_sigs.items():
            m = mult.reindex(sig.index).ffill().fillna(1.0)
            out[code] = (sig.astype(float) * m.astype(float)).astype(float)
        return out
