"""v49_precision_trend: a causal, high-precision trend challenger.

The model deliberately filters *entry episodes*, rather than closing an existing
trade whenever a confirmation flickers.  This makes the win-rate objective an
entry-selection hypothesis, not an artefact of forced early exits.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd


def _load_teachers():
    here = Path(__file__).resolve().parent
    # A ranked run gets the first path copied into its immutable code snapshot.
    # The second path is only a source-tree convenience for local test loading.
    path = next(
        (candidate for candidate in (here / "v48_teachers.py", here.parent / "_shared" / "v48_teachers.py") if candidate.exists()),
        None,
    )
    if path is None:
        raise FileNotFoundError("v49 requires its bundled v48_teachers.py")
    spec = importlib.util.spec_from_file_location("v49_precision_teachers", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_config() -> dict:
    here = Path(__file__).resolve().parent
    for path in (here.parent / "config.json", here / "config.json"):
        if path.exists():
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                pass
    return {}


class SignalEngine:
    """Causal v39d-style trend sleeve with a fixed, pre-registered quality gate.

    The eight score inputs are all available at least one finished bar before an
    entry target.  ``minimum_score=5`` was fixed before evaluation; it is not a
    runtime optimiser and is intentionally the only v49 configuration.
    """

    def __init__(self) -> None:
        cfg = _load_config().get("v49", {})
        self.minimum_score = int(cfg.get("minimum_score", 5))
        if self.minimum_score != 5:
            raise ValueError("v49 has one pre-registered precision gate: minimum_score=5")
        self._teachers = _load_teachers()
        self._trend = self._teachers.TrendTeacher()

    def _entry_gate(self, frame: pd.DataFrame, benchmark: pd.Series | None) -> pd.Series:
        teacher = self._teachers
        data = teacher.normalise_ohlcv(frame)
        close, opening, volume = data["close"], data["open"], data["volume"]
        atr = teacher._atr(data, 14)
        atr_pct = atr / close.replace(0.0, np.nan)
        atr_median = atr_pct.shift(1).expanding(min_periods=20).median()
        typical = (data["high"] + data["low"] + close) / 3.0
        poc = (
            (typical * volume).rolling(20, min_periods=8).sum()
            / volume.rolling(20, min_periods=8).sum().replace(0.0, np.nan)
        ).shift(1)
        volume_ratio = volume.shift(1) / volume.rolling(20, min_periods=8).mean().shift(1)
        fast = teacher._ema(close, 12)
        slow = teacher._ema(close, 26)
        macd_hist = (fast - slow - teacher._ema(fast - slow, 9)).shift(1)
        rs = teacher._relative_strength(close, benchmark)
        prior_close = close.shift(1)
        prior_open = opening.shift(1)
        poc_distance = (prior_close - poc) / atr.shift(1).replace(0.0, np.nan)
        trend_spread = (fast - slow).shift(1) / atr.shift(1).replace(0.0, np.nan)
        return_3 = close.pct_change(3).shift(1)

        components = (
            (rs >= 0.0),                         # relative strength is positive
            (volume_ratio >= 1.0),               # participation is above average
            (prior_close >= prior_open),         # prior finished bar was constructive
            (atr_pct <= 1.25 * atr_median),      # avoid unstable volatility spikes
            poc_distance.between(0.0, 2.5),      # above value, but not extended
            (macd_hist >= 0.0),                  # momentum confirmation
            (trend_spread >= 0.15),              # material fast/slow separation
            (return_3 >= -0.01),                 # no sharp recent reversal
        )
        score = sum(component.fillna(False).astype(int) for component in components)
        return (score >= self.minimum_score).rename("precision_gate")

    def _retain_accepted_episodes(self, base: pd.Series, gate: pd.Series) -> pd.Series:
        """Keep an accepted base trade intact; reject a whole entry episode."""
        active = base.fillna(0.0).gt(0.0)
        accepted = pd.Series(False, index=base.index)
        in_episode = False
        keep_episode = False
        for timestamp, is_active in active.items():
            if not is_active:
                in_episode = False
                keep_episode = False
                continue
            if not in_episode:
                in_episode = True
                keep_episode = bool(gate.loc[timestamp])
            accepted.loc[timestamp] = keep_episode
        return base.where(accepted, 0.0).astype(float)

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        base = self._trend.generate(data_map)
        benchmark = data_map.get("QQQ.US")
        benchmark_close = (
            self._teachers.normalise_ohlcv(benchmark)["close"] if benchmark is not None else None
        )
        return {
            code: self._retain_accepted_episodes(
                base[code], self._entry_gate(frame, benchmark_close).reindex(base[code].index).fillna(False)
            )
            for code, frame in data_map.items()
        }
