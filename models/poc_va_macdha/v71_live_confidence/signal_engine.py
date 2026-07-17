"""v71_live_confidence: live-ready high-WR model with soft confidence sizing.

Hypothesis (pre-registered before holdout eval)
-----------------------------------------------
Wrap v45 Ultimate RSI mean-reversion with:
  1) long-term trend filter (price > SMA(250)) at *entry only*
  2) soft quality floor (min_score >= 1) — weaker than v70 hard gate of 2
  3) continuous confidence from quality + RSI depth → *size*, not skip
  4) optional secondary teacher (v39d) agreement *boosts* size only
  5) modest base scale (22.5% target weight), hard-capped at 35%

Why this should beat prior high-WR arms
---------------------------------------
- v50: 86.5% WR but no confidence channel for live / sizing.
- v70: 91% WR full-window but holdout n collapses under hard quality=2.
- Soft sizing keeps more trades while still concentrating risk on high-conf
  setups — the live operator sees entry_confidence on every trade.

Parameters live in hunt_config.json and must not be retuned after OOS.
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
    here = Path(__file__).resolve().parent
    path = here / "gates.py"
    if not path.exists():
        repo = _find_repo_root(here)
        path = repo / "models" / "poc_va_macdha" / "v71_live_confidence" / "gates.py"
    module_name = f"v71_gates_{id(path)}"
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
    module_name = f"v71_base_{model_name.replace('.', '_')}_{id(path)}"
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
                # deep-merge shallow dict keys used by confidence / quality / trend
                for k, v in overrides.items():
                    if isinstance(v, dict) and isinstance(base.get(k), dict):
                        merged = dict(base[k])
                        merged.update(v)
                        base[k] = merged
                    else:
                        base[k] = v
        except json.JSONDecodeError:
            pass
    return base


class SignalEngine:
    """High-confidence soft-size gate over v45 (+ optional secondary)."""

    def __init__(self) -> None:
        self_dir = Path(__file__).resolve().parent
        repo_root = _find_repo_root(self_dir)
        self._gates = _load_gates_module()
        self._hunt = _load_hunt(self_dir)

        self._base_models: List[str] = list(self._hunt.get("base_models", ["v45_ultimate_rsi"]))
        self._primary: str = str(self._hunt.get("primary", self._base_models[0]))
        secondary = self._hunt.get("secondary")
        self._secondary: Optional[str] = str(secondary) if secondary else None
        if self._secondary and self._secondary not in self._base_models:
            self._base_models.append(self._secondary)

        self._trend_filter: Optional[Dict[str, Any]] = self._hunt.get("trend_filter")
        self._quality_cfg: Dict[str, Any] = dict(self._hunt.get("quality") or {})
        self._conf_cfg: Dict[str, Any] = dict(self._hunt.get("confidence") or {})
        self._stop_loss_pct: float = float(self._hunt.get("stop_loss_pct", 0.0))
        self._signal_scale: float = float(self._hunt.get("signal_scale", 0.225))
        self._max_scale_cap: float = float(self._hunt.get("max_scale_cap", 0.35))
        self._agree_boost: bool = bool(self._hunt.get("secondary_agree_boost", True))
        self._agree_boost_mult: float = float(self._hunt.get("agree_boost_mult", 1.15))

        # Last-run confidence map for live / analysis consumers (code → series).
        self.last_confidence: Dict[str, pd.Series] = {}

        self._engines: Dict[str, Any] = {}
        for name in self._base_models:
            try:
                engine = _load_base_engine(repo_root, name)
                params = self._hunt.get("params", {})
                if params and hasattr(engine, "_params"):
                    engine._params.update(params)
                self._engines[name] = engine
            except Exception as exc:
                print(f"[v71] warning: could not load base engine {name}: {exc}")

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
                print(f"[v71] warning: base engine {name} failed: {exp}")
                base_signals[name] = {}

        quality_on = bool(self._quality_cfg.get("enabled", True))
        min_score = int(self._quality_cfg.get("min_score", 1))
        continuous = False
        if self._trend_filter:
            continuous = str(self._trend_filter.get("apply", "entry")).lower() == "continuous"

        use_rsi = bool(self._conf_cfg.get("use_rsi_depth", True))
        q_w = float(self._conf_cfg.get("quality_weight", 0.65))
        r_w = float(self._conf_cfg.get("rsi_weight", 0.35))
        min_frac = float(self._conf_cfg.get("min_scale_frac", 0.50))
        max_frac = float(self._conf_cfg.get("max_scale_frac", 1.0))

        out: Dict[str, pd.Series] = {}
        self.last_confidence = {}
        for code, df in data_map.items():
            if df is None or df.empty:
                out[code] = pd.Series(0.0, index=pd.DatetimeIndex([]))
                continue

            idx = df.index
            primary = base_signals.get(self._primary, {}).get(code)
            if primary is None or primary.empty:
                primary = pd.Series(0.0, index=idx)
            primary = primary.reindex(idx).fillna(0.0).astype(float)

            # Secondary agreement is optional boost only (never a hard AND gate).
            agree = pd.Series(False, index=idx)
            if self._secondary and self._agree_boost:
                sec = base_signals.get(self._secondary, {}).get(code)
                if sec is not None and not sec.empty:
                    sec = sec.reindex(idx).fillna(0.0).astype(float)
                    agree = (sec > 0.5).fillna(False)

            trend = self._trend_series(data_map, code)

            if quality_on:
                q_score = self._gates.quality_score(df).reindex(idx).fillna(0)
                quality_ok = (q_score >= min_score).fillna(False)
                q_conf = (q_score.astype(float) / 3.0).clip(0.0, 1.0)
            else:
                quality_ok = pd.Series(True, index=idx)
                q_conf = pd.Series(0.7, index=idx)

            rsi_conf = None
            if use_rsi:
                rsi_conf = self._gates.rsi_depth_confidence(df).reindex(idx)

            conf = self._gates.blend_confidence(
                q_conf, rsi_conf, quality_weight=q_w, rsi_weight=r_w
            )

            sized, entry_conf = self._gates.apply_entry_only_soft(
                primary,
                trend=trend,
                quality_ok=quality_ok,
                confidence=conf,
                agree_boost=agree,
                close=df["close"].astype(float),
                stop_loss_pct=self._stop_loss_pct,
                continuous_trend=continuous,
                base_scale=self._signal_scale,
                min_scale_frac=min_frac,
                max_scale_frac=max_frac,
                agree_boost_mult=self._agree_boost_mult,
                max_scale_cap=self._max_scale_cap,
            )
            out[code] = sized
            self.last_confidence[code] = entry_conf

        return out
