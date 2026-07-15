"""v70_high_confidence_wr: highest-confidence high win-rate equity candidate.

Hypothesis (pre-registered before holdout eval):
  Wrap v45 Ultimate RSI mean-reversion with:
    1) long-term trend filter (price > SMA(250)) at *entry only*
    2) causal 3-point quality score (constructive bar, volume, ATR regime)
       requiring min_score >= 2 at entry
    3) modest position scale (22.5% target weight)

Entry selection — not early forced exits — is the win-rate lever.
Parameters live in hunt_config.json and must not be retuned after seeing OOS.

Note: keep module body free of executable top-level statements (backtest
AST sandbox). Gate helpers live in gates.py and are loaded via importlib.
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


def _load_gates_module():
    """Load sibling gates.py without top-level path mutation."""
    here = Path(__file__).resolve().parent
    path = here / "gates.py"
    if not path.exists():
        # Source-tree fallback when run outside a copied code/ snapshot.
        repo = _find_repo_root(here)
        path = repo / "models" / "poc_va_macdha" / "v70_high_confidence_wr" / "gates.py"
    module_name = f"v70_gates_{id(path)}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def _load_base_engine(repo_root: Path, model_name: str) -> Any:
    path = repo_root / "models" / "poc_va_macdha" / model_name / "signal_engine.py"
    if not path.exists():
        raise FileNotFoundError(f"Base engine {model_name} not found at {path}")
    module_name = f"v70_base_{model_name.replace('.', '_')}_{id(path)}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod.SignalEngine()


def _load_hunt(self_dir: Path) -> Dict[str, Any]:
    gates = _load_gates_module()
    base = gates.frozen_defaults()
    hunt_path = self_dir / "hunt_config.json"
    if hunt_path.exists():
        try:
            overrides = json.loads(hunt_path.read_text(encoding="utf-8"))
            if isinstance(overrides, dict):
                base.update(overrides)
        except json.JSONDecodeError:
            pass
    return base


class SignalEngine:
    """High-confidence gate over v45 (+ optional secondary engines)."""

    def __init__(self) -> None:
        self_dir = Path(__file__).resolve().parent
        repo_root = _find_repo_root(self_dir)
        self._gates = _load_gates_module()
        self._hunt = _load_hunt(self_dir)

        self._base_models: List[str] = list(self._hunt.get("base_models", ["v45_ultimate_rsi"]))
        self._primary: str = str(self._hunt.get("primary", self._base_models[0]))
        self._trend_filter: Optional[Dict[str, Any]] = self._hunt.get("trend_filter")
        self._quality_cfg: Dict[str, Any] = dict(self._hunt.get("quality") or {})
        self._stop_loss_pct: float = float(self._hunt.get("stop_loss_pct", 0.0))
        self._signal_scale: float = float(self._hunt.get("signal_scale", 0.225))

        self._engines: Dict[str, Any] = {}
        for name in self._base_models:
            try:
                engine = _load_base_engine(repo_root, name)
                params = self._hunt.get("params", {})
                if params and hasattr(engine, "_params"):
                    engine._params.update(params)
                self._engines[name] = engine
            except Exception as exc:
                print(f"[v70] warning: could not load base engine {name}: {exc}")

    def _trend_series(self, data_map: Dict[str, pd.DataFrame], code: str) -> Optional[pd.Series]:
        if not self._trend_filter:
            return None
        lookback = int(self._trend_filter.get("lookback", 250))
        price_col = str(self._trend_filter.get("price_col", "close"))
        direction = str(self._trend_filter.get("direction", "above")).lower()
        ref_code = self._trend_filter.get("symbol", code)
        df = data_map.get(ref_code)
        if df is None or df.empty or price_col not in df.columns:
            return None
        return self._gates.trend_mask(df[price_col], lookback=lookback, direction=direction)

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        if not self._engines:
            return {code: pd.Series(0.0, index=df.index) for code, df in data_map.items()}

        base_signals: Dict[str, Dict[str, pd.Series]] = {}
        for name, engine in self._engines.items():
            try:
                base_signals[name] = engine.generate(data_map)
            except Exception as exp:
                print(f"[v70] warning: base engine {name} failed: {exp}")
                base_signals[name] = {}

        quality_on = bool(self._quality_cfg.get("enabled", True))
        min_score = int(self._quality_cfg.get("min_score", 2))
        continuous = False
        if self._trend_filter:
            continuous = str(self._trend_filter.get("apply", "entry")).lower() == "continuous"

        out: Dict[str, pd.Series] = {}
        for code, df in data_map.items():
            if df is None or df.empty:
                out[code] = pd.Series(0.0, index=pd.DatetimeIndex([]))
                continue

            idx = df.index
            primary = base_signals.get(self._primary, {}).get(code)
            if primary is None or primary.empty:
                primary = pd.Series(0.0, index=idx)
            primary = primary.reindex(idx).fillna(0.0).astype(float)

            trend = self._trend_series(data_map, code)
            if quality_on:
                q = self._gates.quality_gate(df, min_score=min_score).reindex(idx).fillna(False)
            else:
                q = pd.Series(True, index=idx)

            gated = self._gates.apply_entry_only_gates(
                primary,
                trend=trend,
                quality=q,
                close=df["close"].astype(float),
                stop_loss_pct=self._stop_loss_pct,
                continuous_trend=continuous,
            )
            out[code] = gated * self._signal_scale

        return out
