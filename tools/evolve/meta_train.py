"""Phase 4: walk-forward meta MLP for take/skip (utility labels).

Does not replace primary SIDE. Trains on features → P(positive next return)
as a soft size mult recipe. Never tunes on pure OOS fold.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))


def _try_import_feature_evolve():
    import feature_evolve_1k as fe  # noqa: WPS433

    return fe


def fetch_frames(codes: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    """Pull daily OHLCV via yfinance for feature mining."""
    import yfinance as yf

    frames: dict[str, pd.DataFrame] = {}
    for code in codes:
        ticker = code.replace(".US", "")
        try:
            df = yf.download(
                ticker,
                start=start,
                end=end,
                interval="1d",
                progress=False,
                auto_adjust=True,
            )
        except Exception:
            continue
        if df is None or df.empty:
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0].lower() for c in df.columns]
        else:
            df.columns = [str(c).lower() for c in df.columns]
        need = {"open", "high", "low", "close"}
        if not need.issubset(set(df.columns)):
            continue
        if "volume" not in df.columns:
            df["volume"] = 1.0
        frames[code] = df
    return frames


def train_meta_recipe(
    codes: list[str],
    *,
    start: str,
    end: str,
    out_dir: Path,
    n_splits: int = 4,
) -> dict[str, Any]:
    """Mine features + train sklearn MLP; write META_RECIPE.json."""
    fe = _try_import_feature_evolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    raw = fetch_frames(codes, start, end)
    if len(raw) < 2:
        return {"ok": False, "error": "insufficient_price_data", "n_symbols": len(raw)}

    frames = {k: fe.build_features(v) for k, v in raw.items()}
    diag = fe.feature_diagnostics(frames)
    selected = [r["feature"] for r in diag if r.get("selected")][:12]
    if not selected:
        selected = [r["feature"] for r in diag[:8]]

    meta = fe.train_meta_mlp(frames, selected, n_splits=n_splits)
    if meta.get("error"):
        return {"ok": False, "error": meta["error"]}

    # Utility-style summary from feature_evolve_1k.train_meta_mlp
    recipe = {
        "ok": True,
        "role": "secondary_meta_only",
        "forbid": ["replace_primary_side"],
        "selected_features": selected,
        "feature_diagnostics_top": diag[:15],
        "mlp": {
            "mean_accuracy": meta.get("mean_fold_acc"),
            "mean_auc": meta.get("mean_fold_auc"),
            "oos_sharpe_long_filter": meta.get("oos_sharpe_long_filter"),
            "buy_hold_sharpe": meta.get("buy_hold_sharpe"),
            "n_rows": meta.get("n_rows"),
            "folds": meta.get("folds"),
            "live_rule": meta.get("live_rule"),
            "mlp_note": (meta.get("mlp") or {}).get("note"),
        },
        "size_rule": {
            "description": "If meta P(up) >= 0.55 size=1.0; 0.45-0.55 size=0.5; else skip",
            "thresholds": {"full": 0.55, "half": 0.45},
        },
        "window": {"start": start, "end": end},
        "codes": codes,
    }

    # Strip non-JSON objects
    def _clean(o: Any) -> Any:
        if isinstance(o, dict):
            return {k: _clean(v) for k, v in o.items() if not callable(v) and k != "model"}
        if isinstance(o, list):
            return [_clean(x) for x in o]
        if isinstance(o, (np.floating, float)):
            x = float(o)
            return x if math.isfinite(x) else None
        if isinstance(o, (np.integer, int)):
            return int(o)
        if isinstance(o, (str, bool)) or o is None:
            return o
        return str(o)

    recipe = _clean(recipe)
    path = out_dir / "META_RECIPE.json"
    path.write_text(json.dumps(recipe, indent=2))
    (out_dir / "FEATURE_DIAGNOSTICS.json").write_text(json.dumps(_clean(diag[:40]), indent=2))
    return recipe
