"""Soft-confluence specialist for APLD (ai_infra_beta).

Uses CRWV-style score sizing instead of hard-AND gate stacks.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Dict

import pandas as pd

_SHARED = Path(__file__).resolve().parents[2] / "_shared" / "soft_specialist_engine.py"
if not _SHARED.exists():
    _SHARED = Path(__file__).resolve().parents[2] / "_shared" / "soft_specialist_engine.py"

_spec = importlib.util.spec_from_file_location("soft_specialist_engine_apld", _SHARED)
_mod = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_mod)


def _resample_ohlcv(df, rule: str):
    return _mod._resample_ohlcv(df, rule)


def _prior_session_profile(df, lookback=20, rows=25, value_area_pct=0.7):
    return _mod._prior_session_profile(df, lookback, rows, value_area_pct)


def _htf_ha_green(df, htf, fast=12, slow=26, signal=9):
    return _mod._htf_ha_green(df, htf, fast, slow, signal)


def volume_price_state(df, look=5, vol_sma=20):
    return _mod.volume_price_state(df, look, vol_sma)


def squeeze_momentum(df, length=20, mult_bb=2.0, length_kc=20, mult_kc=1.5):
    return _mod.squeeze_momentum(df, length, mult_bb, length_kc, mult_kc)


def dynamic_swing_anchored_vwap(df, swing_period=50):
    return _mod.dynamic_swing_anchored_vwap(df, swing_period)


class SignalEngine(_mod.SoftSpecialistEngine):
    def __init__(self, **kwargs):
        cfg = _mod.load_cfg_from_model_dir(Path(__file__).resolve().parent)
        merged = {
            "thesis": "ai_infra_beta",
            "symbols": ["APLD"],
            **{k: cfg[k] for k in (
                "min_score", "signal_tf", "macd_htf", "stop_atr", "trail_atr",
                "arm_trail_atr", "max_hold_bars", "demand_atr_band", "profile_lookback",
                "value_area_pct", "put_walls",
            ) if k in cfg},
            **kwargs,
        }
        super().__init__(**merged)

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        return super().generate(data_map)
