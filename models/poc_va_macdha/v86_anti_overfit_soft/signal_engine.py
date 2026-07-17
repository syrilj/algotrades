"""v86_anti_overfit_soft: v72 dual-sleeve with a soft anti-overfit overlay.

Overlay rules (pre-registered, no retuning):
  1. Drop SPY from the long book.
  2. For every other symbol, scale the v72 target weight by a confidence
     derived from volume expansion and absence of a red-flag-up bar at entry.
     - Filter passes  -> 100% of the v72 weight.
     - Filter fails   -> 50% of the v72 weight.

This treats the anti-overfit stress signal as a position-sizing input rather
than a hard gate, preserving v72's trades while reducing exposure on the
low-confidence bars the ledger stress identified as fragile.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict

import pandas as pd


def _find_repo_root(anchor: Path) -> Path:
    for p in anchor.resolve().parents:
        if (p / "models" / "poc_va_macdha").exists():
            return p
    raise RuntimeError("Could not find TradingAlgoWork repo root")


def _load_model_module(repo_root: Path, model_name: str) -> Any:
    """Load a sibling model's signal_engine.py as an importable module."""
    path = repo_root / "models" / "poc_va_macdha" / model_name / "signal_engine.py"
    if not path.exists():
        raise FileNotFoundError(f"Base engine {model_name} not found at {path}")
    module_name = f"v86_base_{model_name.replace('.', '_')}_{id(path)}"
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def _resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    agg = {c: ("first" if c == "open" else "max" if c == "high" else "min" if c == "low" else "last" if c == "close" else "sum") for c in cols}
    return df[cols].resample(rule, label="right", closed="right").agg(agg).dropna(subset=["close"])


class SignalEngine:
    """Wrap v72 and apply a frozen anti-overfit soft-size overlay."""

    def __init__(self):
        self_dir = Path(__file__).resolve().parent
        repo_root = _find_repo_root(self_dir)

        self._v72 = _load_model_module(repo_root, "v72_dual_sleeve").SignalEngine()
        self._v39d = _load_model_module(repo_root, "v39d_confluence")

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        out = self._v72.generate(data_map)

        for code, df in data_map.items():
            sig = out.get(code)
            if sig is None or sig.empty:
                continue

            # Rule 1: SPY is too noisy/pinned; exclude it.
            if code == "SPY.US":
                out[code] = pd.Series(0.0, index=df.index)
                continue

            # Rule 2: soft-size by VPA confidence.
            cfg = getattr(self._v39d, "_ROUTING", {}).get(code, {})
            look = int(cfg.get("vol_look", 5))
            vol_sma = int(cfg.get("vol_sma", 20))
            signal_tf = cfg.get("signal_tf")

            frame = _resample_ohlcv(df, signal_tf) if signal_tf else df
            vp = self._v39d.volume_price_state(frame, look=look, vol_sma=vol_sma)
            mask = vp["vol_expand"].fillna(False) & (~vp["red_flag_up"].fillna(True))
            if signal_tf:
                mask = mask.reindex(df.index, method="ffill").fillna(False)

            # 1.0 when filter passes, 0.5 when it fails
            scale = mask.astype(float).replace({0.0: 0.5, 1.0: 1.0})
            out[code] = (sig * scale).astype(float)

        return out
