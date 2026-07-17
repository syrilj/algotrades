"""v85_anti_overfit: v39d_confluence base with a frozen anti-overfit overlay.

Overlay rules (pre-registered, no retuning):
  1. Drop SPY from the long book.
  2. For every other symbol, require volume expansion and no "red flag up" bar
     at the entry bar.

The frozen gate set is derived from anti-overfit stress on the v39d candidate
ledger: the combination of f_vol_expand, !f_block_red_flag_on and excluding
SPY produced stable holdout expectancy across multiple lock dates.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict

import pandas as pd


def _resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample OHLCV to the requested rule (same logic as v39d base)."""
    cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    return (
        df[cols]
        .resample(rule, label="right", closed="right")
        .agg({c: ("first" if c == "open" else "max" if c == "high" else "min" if c == "low" else "last" if c == "close" else "sum") for c in cols})
        .dropna(subset=["close"])
    )


class SignalEngine:
    """Wrap v39d_confluence and apply a frozen post-generation filter."""

    def __init__(self):
        # Vendored v39d engine is copied into the run code directory by
        # DEPENDENCIES.json.  Make sure that directory is importable, then load
        # the base engine.  This is done inside __init__ because the backtest
        # runner's AST sandbox rejects top-level executable statements.
        import sys

        code_dir = Path(__file__).resolve().parent
        if str(code_dir) not in sys.path:
            sys.path.insert(0, str(code_dir))
        import v39d_engine as base  # noqa: F401

        self._base = base.SignalEngine()
        self._base_module = base

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        out = self._base.generate(data_map)
        base = self._base_module

        for code, df in data_map.items():
            sig = out.get(code)
            if sig is None or sig.empty:
                continue

            # Rule 1: SPY is too noisy/pinned; the ledger stress says exclude it.
            if code == "SPY.US":
                out[code] = pd.Series(0.0, index=df.index)
                continue

            # Already flat/dropped by base engine.
            if code in getattr(base, "REGIME_FLAT", set()) or code in getattr(
                base, "TRADE_DROP", set()
            ):
                continue

            # Rule 2: require volume expansion and no red-flag-up at entry.
            cfg = getattr(base, "_ROUTING", {}).get(code, {})
            look = int(cfg.get("vol_look", 5))
            vol_sma = int(cfg.get("vol_sma", 20))
            signal_tf = cfg.get("signal_tf")

            # Compute VPA on the same time frame the base engine used.
            frame = _resample_ohlcv(df, signal_tf) if signal_tf else df
            vp = base.volume_price_state(frame, look=look, vol_sma=vol_sma)
            mask = vp["vol_expand"].fillna(False) & (~vp["red_flag_up"].fillna(True))
            if signal_tf:
                mask = mask.reindex(df.index, method="ffill").fillna(False)

            out[code] = sig.where(mask, 0.0).astype(float)

        return out
