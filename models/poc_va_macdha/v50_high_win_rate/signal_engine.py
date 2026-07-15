"""v50_high_win_rate: gate v45 mean-reversion signals with trend + sizing.

- Entry only when v45 fires and the long-term trend filter is satisfied.
- Optional hard stop-loss per trade (set via stop_loss_pct in hunt_config).
- No re-entry while the same v45 episode is active.
- Supports 'entry' (filter only at entry) or 'continuous' trend mode.
- Supports a signal_scale factor to cap position size per trade.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


def _find_repo_root(anchor: Path) -> Path:
    for p in anchor.resolve().parents:
        if (p / "models" / "poc_va_macdha").exists():
            return p
    raise RuntimeError("Could not find TradingAlgoWork repo root")


def _load_base_engine(repo_root: Path, model_name: str) -> Any:
    """Import the SignalEngine class from a sibling model directory."""
    path = repo_root / "models" / "poc_va_macdha" / model_name / "signal_engine.py"
    if not path.exists():
        raise FileNotFoundError(f"Base engine {model_name} not found at {path}")
    module_name = f"base_{model_name.replace('.', '_')}_{id(path)}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[arg-type]
    return mod.SignalEngine()


class SignalEngine:
    """High-confidence gate over one primary and optional secondary engines."""

    def __init__(self) -> None:
        self_dir = Path(__file__).resolve().parent
        repo_root = _find_repo_root(self_dir)

        hunt_path = self_dir / "hunt_config.json"
        self._hunt = json.loads(hunt_path.read_text(encoding="utf-8")) if hunt_path.exists() else {}

        self._base_models: List[str] = list(self._hunt.get("base_models", []))
        self._primary: str = str(self._hunt.get("primary", self._base_models[0] if self._base_models else ""))
        self._mode: str = str(self._hunt.get("mode", "and"))
        self._threshold: float = float(self._hunt.get("threshold", 0.5))
        self._trend_filter: Optional[Dict[str, Any]] = self._hunt.get("trend_filter")
        self._stop_loss_pct: float = float(self._hunt.get("stop_loss_pct", 0.0))
        self._signal_scale: float = float(self._hunt.get("signal_scale", 1.0))

        self._engines: Dict[str, Any] = {}
        for name in self._base_models:
            try:
                engine = _load_base_engine(repo_root, name)
                # Allow base-engine parameter overrides from hunt_config.
                params = self._hunt.get("params", {})
                if params and hasattr(engine, "_params"):
                    engine._params.update(params)
                self._engines[name] = engine
            except Exception as exc:
                print(f"[v50] warning: could not load base engine {name}: {exc}")

    def _trend_series(self, data_map: Dict[str, pd.DataFrame], code: str) -> Optional[pd.Series]:
        if not self._trend_filter:
            return None
        lookback = int(self._trend_filter.get("lookback", 200))
        price_col = str(self._trend_filter.get("price_col", "close"))
        direction = str(self._trend_filter.get("direction", "above")).lower()
        ref_code = self._trend_filter.get("symbol", code)

        df = data_map.get(ref_code)
        if df is None or df.empty or price_col not in df.columns:
            return None
        price = df[price_col].astype(float)
        sma = price.rolling(lookback, min_periods=max(1, lookback // 2)).mean()
        if direction == "above":
            return price > sma
        if direction == "below":
            return price < sma
        return None

    def _combine_signals(self, sigs: Dict[str, pd.Series], idx: pd.Index) -> pd.Series:
        primary = sigs.get(self._primary, pd.Series(0.0, index=idx))

        if self._mode == "and":
            gate = pd.Series(True, index=idx)
            for name, sig in sigs.items():
                if name == self._primary:
                    continue
                gate = gate & (sig > self._threshold)
            signal = (primary > 0.5) & gate
        elif self._mode == "weighted":
            weights = self._hunt.get("weights", {})
            total = 0.0
            weighted = pd.Series(0.0, index=idx)
            for name, sig in sigs.items():
                w = float(weights.get(name, 1.0 / len(self._base_models)))
                weighted += sig * w
                total += w
            signal = (weighted / total) > self._threshold if total > 0 else primary > 0.5
        else:
            signal = primary > 0.5

        return signal

    def _generate_one(
        self, primary: pd.Series, trend: Optional[pd.Series], close: pd.Series
    ) -> pd.Series:
        """State machine that applies trend filter and stop loss."""
        idx = primary.index
        primary = primary.reindex(idx).fillna(0.0).astype(float)
        close = close.reindex(idx).astype(float)
        if trend is None:
            trend = pd.Series(True, index=idx)
        else:
            trend = trend.reindex(idx).fillna(False)

        apply = "continuous"
        if self._trend_filter:
            apply = str(self._trend_filter.get("apply", "continuous")).lower()

        stop_pct = self._stop_loss_pct
        trigger = 1.0 - stop_pct if stop_pct > 0 else 0.0

        in_pos = False
        entry_price = 0.0
        prev_primary = 0.0
        out = pd.Series(0.0, index=idx)

        for i in range(len(idx)):
            p = primary.iloc[i]
            c = close.iloc[i]
            t = trend.iloc[i]
            new_entry = (p > 0.5) and (prev_primary <= 0.5) and t

            if not in_pos:
                if new_entry:
                    in_pos = True
                    entry_price = c
            else:
                exit_now = False
                if p <= 0.5:
                    exit_now = True
                elif stop_pct > 0 and c < entry_price * trigger:
                    exit_now = True
                elif apply == "continuous" and not t:
                    exit_now = True

                if exit_now:
                    in_pos = False

            out.iloc[i] = 1.0 if in_pos else 0.0
            prev_primary = p

        return out

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        if not self._engines:
            return {code: pd.Series(0.0, index=df.index) for code, df in data_map.items()}

        base_signals: Dict[str, Dict[str, pd.Series]] = {}
        for name, engine in self._engines.items():
            try:
                base_signals[name] = engine.generate(data_map)
            except Exception as exc:
                print(f"[v50] warning: base engine {name} failed: {exc}")
                base_signals[name] = {}

        out: Dict[str, pd.Series] = {}
        for code, df in data_map.items():
            if df is None or df.empty:
                out[code] = pd.Series(0.0, index=pd.DatetimeIndex([]))
                continue

            idx = df.index
            sigs: Dict[str, pd.Series] = {}
            for name in self._base_models:
                sig = base_signals[name].get(code)
                if sig is None or sig.empty:
                    sig = pd.Series(0.0, index=idx)
                sigs[name] = sig.reindex(idx).fillna(0.0).astype(float)

            primary = self._combine_signals(sigs, idx)
            trend = self._trend_series(data_map, code)
            close = df["close"].astype(float)
            out[code] = self._generate_one(primary, trend, close) * self._signal_scale

        return out
