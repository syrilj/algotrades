"""v88_xgb_filter: v72_dual_sleeve + frozen XGB trade filter as a ranker/sizer.

RESEARCH ONLY — NOT PROMOTED. Never route live capital through this engine
until it has cleared the same promotion gates as every other model
(locked-holdout pass bar, findings record, manifest review).

Design (pre-registered before the one-shot holdout eval):
  1. Generate v72_dual_sleeve target weights unchanged.
  2. At each fresh entry (flat → long transition) score the bar with the
     frozen booster from ``models/poc_va_macdha/v88_xgb_filter/xgb_filter.json``
     (trained by tools/ml_filter/train_xgb.py on train-window candidates only).
  3. **Ranker, not gate** (plan P2-9): entries scoring below the frozen
     threshold keep the trade but at ``low_scale`` (default 0.5) of the v72
     weight for the whole holding segment; entries at/above threshold keep
     full weight. No entry is ever added that v72 did not signal.

Fail-soft: if xgboost, the model file, or its metadata are unavailable, the
engine returns raw v72 weights (identical behavior) and reports
``filter_active = False`` — a broken filter must never change the book.
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
    module_name = f"v88_base_{model_name}_{id(path)}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod.SignalEngine()


def scale_segments(
    weights: pd.Series,
    p_win_at_entry: Dict[int, float],
    *,
    threshold: float,
    low_scale: float,
    high_scale: float = 1.0,
    max_cap: float = 0.50,
) -> pd.Series:
    """Scale each holding segment by its entry score (pure, testable).

    ``p_win_at_entry`` maps the integer position of each fresh entry bar to
    its P(win). Segments whose entry has no score (feature warmup, model
    miss) keep full weight — fail-soft, never fail-closed into zero risk the
    base engine intended to take.
    """
    values = weights.fillna(0.0).astype(float).to_numpy().copy()
    long_now = values > 1e-9
    n = len(values)
    t = 0
    while t < n:
        if long_now[t] and (t == 0 or not long_now[t - 1]):
            end = t
            while end < n and long_now[end]:
                end += 1
            score = p_win_at_entry.get(t)
            if score is not None:
                if float(score) >= threshold:
                    values[t:end] = np.minimum(max_cap, values[t:end] * high_scale)
                else:
                    values[t:end] = np.minimum(0.50, values[t:end] * low_scale)
            t = end
        else:
            t += 1
    return pd.Series(values, index=weights.index)


class SignalEngine:
    """v72 weights, re-ranked by the frozen XGB filter at entry time."""

    def __init__(self) -> None:
        self_dir = Path(__file__).resolve().parent
        repo_root = _find_repo_root(self_dir)
        self._repo_root = repo_root
        self._base = _load_base_engine(repo_root, "v72_dual_sleeve")

        bundle_dir = repo_root / "models" / "poc_va_macdha" / "v88_xgb_filter"
        self._booster = None
        self._features: list[str] = []
        self._threshold = 0.5
        self._low_scale = 0.75
        self._high_scale = 1.00
        self._max_cap = 0.50
        try:
            meta = json.loads((bundle_dir / "filter_meta.json").read_text(encoding="utf-8"))
            self._features = list(meta["features"])
            self._threshold = float(meta["threshold"])
            hunt_path = self_dir / "hunt_config.json"
            if hunt_path.exists():
                hunt = json.loads(hunt_path.read_text(encoding="utf-8"))
                self._low_scale = float(hunt.get("low_scale", self._low_scale))
                self._high_scale = float(hunt.get("high_scale", self._high_scale))
                self._max_cap = float(hunt.get("max_cap", self._max_cap))
            import xgboost as xgb

            booster = xgb.Booster()
            booster.load_model(str(bundle_dir / "xgb_filter.json"))
            self._booster = booster
        except Exception as exc:  # noqa: BLE001
            print(f"[v88] warning: filter unavailable, passing through raw v72 weights: {exc}")

        self.filter_active = self._booster is not None
        self.last_confidence: Dict[str, pd.Series] = {}
        self.last_sleeve: Dict[str, pd.Series] = {}
        self.last_p_win: Dict[str, pd.Series] = {}

    def _score_entries(
        self,
        frame: pd.DataFrame,
        weights: pd.Series,
        conf: Optional[pd.Series],
        sleeve: Optional[pd.Series],
        spy_close: Optional[pd.Series],
        symbol: str,
    ) -> Dict[int, float]:
        sys.path.insert(0, str(self._repo_root / "tools"))
        from ml_filter.features import compute_feature_frame

        features = compute_feature_frame(
            frame, symbol=symbol, engine_conf=conf, sleeve=sleeve, spy_close=spy_close
        )
        values = weights.reindex(frame.index).fillna(0.0).astype(float).to_numpy()
        long_now = values > 1e-9
        entry_positions = [
            t for t in range(len(values)) if long_now[t] and (t == 0 or not long_now[t - 1])
        ]
        scores: Dict[int, float] = {}
        if not entry_positions or self._booster is None:
            return scores
        rows = features.iloc[entry_positions][self._features]
        valid_mask = ~rows.isna().any(axis=1)
        valid_positions = [p for p, ok in zip(entry_positions, valid_mask.to_numpy()) if ok]
        if not valid_positions:
            return scores
        import xgboost as xgb

        preds = self._booster.predict(
            xgb.DMatrix(rows[valid_mask.to_numpy()].to_numpy(dtype=float), feature_names=self._features)
        )
        for position, p_win in zip(valid_positions, preds):
            scores[position] = float(p_win)
        return scores

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        base_out = self._base.generate(data_map)
        conf_map = getattr(self._base, "last_confidence", {}) or {}
        sleeve_map = getattr(self._base, "last_sleeve", {}) or {}
        spy_frame = data_map.get("SPY.US")
        spy_close = spy_frame["close"] if spy_frame is not None and "close" in spy_frame else None

        out: Dict[str, pd.Series] = {}
        self.last_confidence = {}
        self.last_sleeve = {}
        self.last_p_win = {}
        for code, frame in data_map.items():
            weights = base_out.get(code)
            if weights is None or frame is None or frame.empty:
                out[code] = weights if weights is not None else pd.Series(dtype=float)
                continue
            weights = weights.reindex(frame.index).fillna(0.0).astype(float)
            if self._booster is None:
                out[code] = weights
            else:
                try:
                    scores = self._score_entries(
                        frame, weights, conf_map.get(code), sleeve_map.get(code), spy_close, code
                    )
                    out[code] = scale_segments(
                        weights,
                        scores,
                        threshold=self._threshold,
                        low_scale=self._low_scale,
                        high_scale=self._high_scale,
                        max_cap=self._max_cap,
                    )
                    p_series = pd.Series(np.nan, index=frame.index)
                    for position, p_win in scores.items():
                        p_series.iloc[position] = p_win
                    self.last_p_win[code] = p_series
                except Exception as exc:  # noqa: BLE001
                    print(f"[v88] warning: scoring failed for {code}, raw weights kept: {exc}")
                    out[code] = weights
            if code in conf_map:
                self.last_confidence[code] = conf_map[code]
            if code in sleeve_map:
                self.last_sleeve[code] = sleeve_map[code]
        return out
