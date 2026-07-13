"""Standalone regime reader — no repo imports outside pandas/stdlib.

Copied into run code dirs by loop_core if needed.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


_ROOT = Path(__file__).resolve().parents[2]
_SPEC_PATH = _ROOT / "models" / "_shared" / "REGIME_SPEC.json"


def _default_parquet() -> Path:
    if _SPEC_PATH.exists():
        try:
            spec = json.loads(_SPEC_PATH.read_text())
            return _ROOT / spec.get("default_parquet", "models/_shared/regime/regime_daily.parquet")
        except Exception:
            pass
    return _ROOT / "models" / "_shared" / "regime" / "regime_daily.parquet"


def regime_at(date, parquet_path=None) -> dict | None:
    """Return last row with index <= date - 1 day (t-1 lag)."""
    path = Path(parquet_path) if parquet_path else _default_parquet()
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    ts = pd.Timestamp(date) - pd.Timedelta(days=1)
    rows = df[df.index <= ts]
    if rows.empty:
        return None
    row = rows.iloc[-1]
    return {k: row[k] for k in row.index}


def gate(symbol: str, date, sector_map: dict, parquet_path=None) -> dict:
    """Return regime gate result for a symbol at ``date``.

    sector_map: symbol -> sector ETF (e.g. TSLA.US -> XLY.US)
    """
    reg = regime_at(date, parquet_path) or {}
    score = float(reg.get("score", 0.0))
    label = str(reg.get("label", "neutral"))
    index_ok = label != "risk_off" and score > -0.5

    sector = str(sector_map.get(symbol, ""))
    sector_col = f"sector_ok_{sector}"
    sector_ok = bool(reg.get(sector_col, True)) if sector else True

    return {
        "index_ok": index_ok,
        "sector_ok": sector_ok,
        "regime": label,
        "score": score,
    }


def regime_label_at(date, parquet_path=None) -> str | None:
    r = regime_at(date, parquet_path)
    return r.get("label") if r else None
