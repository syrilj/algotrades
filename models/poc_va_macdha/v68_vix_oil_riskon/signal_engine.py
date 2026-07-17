"""v68_vix_oil_riskon: enter high-beta only when VIX and oil are falling.

Wraps frozen v39d_confluence. Thesis: declining VIX + declining oil signals
risk-on / SPY rebound; high-beta names (IONQ, etc.) should only be entered
in that regime.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Set

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
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod.SignalEngine()


def _load_daily_close(path: Path) -> Optional[pd.Series]:
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if "close" not in df.columns:
        return None
    s = df["close"].astype(float).copy()
    s.index = pd.to_datetime(s.index).tz_localize(None)
    s = s.sort_index()
    s = s[~s.index.duplicated(keep="last")]
    return s


def _declining_gate(close: pd.Series, lookback: int) -> pd.Series:
    """True when price has fallen over `lookback` days, using t-1 info only.

    gate[t] uses close[t-1] vs close[t-1-lookback] so the signal is known
    before bar t (causal for daily; reindex+ffill for hourly).
    """
    # Fully lag by 1 day so we never use same-day close in the decision.
    lagged = close.shift(1)
    prior = lagged.shift(lookback)
    gate = lagged < prior
    return gate.fillna(False)


class SignalEngine:
    def __init__(self) -> None:
        self_dir = Path(__file__).resolve().parent
        self._repo_root = _find_repo_root(self_dir)
        hunt_path = self_dir / "hunt_config.json"
        self._hunt: Dict[str, Any] = (
            json.loads(hunt_path.read_text(encoding="utf-8")) if hunt_path.exists() else {}
        )

        primary = str(self._hunt.get("primary", "v39d_confluence"))
        self._base = _load_base_engine(self._repo_root, primary)

        self._lookback = int(self._hunt.get("lookback_days", 5))
        self._require_vix = bool(self._hunt.get("require_vix_down", True))
        self._require_oil = bool(self._hunt.get("require_oil_down", True))
        self._high_beta_only = bool(self._hunt.get("high_beta_only", True))
        self._high_beta: Set[str] = set(
            self._hunt.get(
                "high_beta_codes",
                ["IONQ.US", "APLD.US", "TSLA.US", "MU.US"],
            )
        )
        self._gate_mode = str(self._hunt.get("gate_mode", "hard")).lower()
        self._soft_size = float(self._hunt.get("soft_size", 0.25))

        vix_rel = self._hunt.get("vix_path", "data_cache/1d/VIX.parquet")
        oil_rel = self._hunt.get("oil_path", "data_cache/1d/USO.parquet")
        self._vix = _load_daily_close(self._repo_root / vix_rel)
        self._oil = _load_daily_close(self._repo_root / oil_rel)

        self._risk_on_daily = self._build_risk_on_daily()

    def _build_risk_on_daily(self) -> Optional[pd.Series]:
        parts = []
        if self._require_vix:
            if self._vix is None or self._vix.empty:
                print("[v68] warning: VIX series missing; risk-on gate disabled")
                return None
            parts.append(_declining_gate(self._vix, self._lookback))
        if self._require_oil:
            if self._oil is None or self._oil.empty:
                print("[v68] warning: oil series missing; risk-on gate disabled")
                return None
            parts.append(_declining_gate(self._oil, self._lookback))
        if not parts:
            return None
        combine = str(self._hunt.get("combine", "and")).lower()
        gate = parts[0]
        for p in parts[1:]:
            # Align on union of trading days (VIX/USO usually match).
            gate = gate.reindex(gate.index.union(p.index)).fillna(False)
            p2 = p.reindex(gate.index).fillna(False)
            gate = (gate | p2) if combine == "or" else (gate & p2)
        return gate.astype(bool)

    def _risk_on_on_index(self, idx: pd.Index) -> pd.Series:
        if self._risk_on_daily is None or self._risk_on_daily.empty:
            return pd.Series(True, index=idx)
        daily = self._risk_on_daily.copy()
        daily.index = pd.to_datetime(daily.index).tz_localize(None)
        # Map each bar timestamp to the latest known daily gate (ffill).
        bar_days = pd.to_datetime(idx).tz_localize(None)
        # reindex to bar index via asof: convert to Series of dates
        s = daily.astype(float)
        # Build a daily series reindexed to bar timestamps with ffill
        # Use merge_asof style: reindex to unique days then map
        try:
            aligned = s.reindex(bar_days, method="ffill")
            aligned.index = idx
            return aligned.fillna(0.0).astype(float) > 0.5
        except Exception:
            # Fallback: date floor join
            day_index = pd.DatetimeIndex(bar_days.normalize())
            mapped = s.reindex(day_index, method="ffill")
            mapped.index = idx
            return mapped.fillna(0.0).astype(float) > 0.5

    def _apply_entry_gate(
        self, base_sig: pd.Series, risk_on: pd.Series, hard: bool
    ) -> pd.Series:
        """Entry-only gate: block/size-down new longs when not risk-on.

        Hold until base signal exits. Soft mode sizes blocked entries to soft_size.
        """
        idx = base_sig.index
        base = base_sig.reindex(idx).fillna(0.0).astype(float)
        risk = risk_on.reindex(idx).fillna(False)
        soft = self._soft_size

        out = pd.Series(0.0, index=idx)
        in_pos = False
        scale = 1.0
        prev = 0.0
        for i in range(len(idx)):
            b = float(base.iloc[i])
            r = bool(risk.iloc[i])
            new_entry = (b > 0.5) and (prev <= 0.5)
            if not in_pos:
                if new_entry:
                    if r:
                        in_pos = True
                        scale = 1.0
                        out.iloc[i] = b * scale
                    elif not hard:
                        in_pos = True
                        scale = soft
                        out.iloc[i] = b * scale
                    else:
                        out.iloc[i] = 0.0
                else:
                    out.iloc[i] = 0.0
            else:
                if b <= 0.5:
                    in_pos = False
                    scale = 1.0
                    out.iloc[i] = 0.0
                else:
                    out.iloc[i] = b * scale
            prev = b
        return out

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        base_sigs = self._base.generate(data_map)
        hard = self._gate_mode != "soft"
        out: Dict[str, pd.Series] = {}

        for code, df in data_map.items():
            base = base_sigs.get(code)
            if base is None or base.empty:
                out[code] = pd.Series(0.0, index=df.index if df is not None else [])
                continue

            apply_gate = (not self._high_beta_only) or (code in self._high_beta)
            if not apply_gate:
                out[code] = base.astype(float)
                continue

            risk_on = self._risk_on_on_index(base.index)
            out[code] = self._apply_entry_gate(base, risk_on, hard=hard)

        return out
