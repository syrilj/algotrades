"""Canonical daily-bar schema and frame normalization."""

from __future__ import annotations

from typing import Sequence

import pandas as pd

REQUIRED_COLUMNS: tuple[str, ...] = (
    "permanent_security_id",
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "adjusted_open",
    "adjusted_high",
    "adjusted_low",
    "adjusted_close",
    "adjusted_volume",
    "split_factor",
    "cash_dividend",
    "exchange",
    "security_type",
    "is_delisted",
    "delisting_date",
    "vendor_timestamp",
    "sector",
)

PRICE_COLS = ("open", "high", "low", "close")
ADJ_PRICE_COLS = (
    "adjusted_open",
    "adjusted_high",
    "adjusted_low",
    "adjusted_close",
)


def empty_bars_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=list(REQUIRED_COLUMNS))


def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in REQUIRED_COLUMNS:
        if col not in out.columns:
            if col in PRICE_COLS or col in ADJ_PRICE_COLS or col in ("volume", "adjusted_volume"):
                out[col] = float("nan")
            elif col == "split_factor":
                out[col] = 1.0
            elif col == "cash_dividend":
                out[col] = 0.0
            elif col == "is_delisted":
                out[col] = False
            elif col == "delisting_date":
                out[col] = pd.NaT
            elif col == "sector":
                out[col] = "UNKNOWN"
            elif col == "exchange":
                out[col] = "UNKNOWN"
            elif col == "security_type":
                out[col] = "common_stock"
            elif col == "vendor_timestamp":
                out[col] = None
            else:
                out[col] = None
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    return out[list(REQUIRED_COLUMNS)]


def from_ohlcv(
    df: pd.DataFrame,
    *,
    symbol: str,
    permanent_security_id: str | None = None,
    exchange: str = "UNKNOWN",
    security_type: str = "common_stock",
    sector: str = "UNKNOWN",
) -> pd.DataFrame:
    """Normalize a simple OHLCV frame (index=date or date column) into canonical schema."""
    raw = df.copy()
    if "date" not in raw.columns:
        raw = raw.reset_index()
        # common index names
        for cand in ("timestamp", "Datetime", "Date", "index", "date"):
            if cand in raw.columns:
                raw = raw.rename(columns={cand: "date"})
                break
        if "date" not in raw.columns and len(raw.columns):
            raw = raw.rename(columns={raw.columns[0]: "date"})
    cols = {c.lower(): c for c in raw.columns}
    mapping = {}
    for need in ("open", "high", "low", "close", "volume"):
        if need in cols:
            mapping[cols[need]] = need
    raw = raw.rename(columns=mapping)
    for c in ("open", "high", "low", "close", "volume"):
        if c not in raw.columns:
            raise ValueError(f"{symbol}: missing column {c}")
    sid = permanent_security_id or f"SID_{symbol.upper().replace('.', '_')}"
    out = pd.DataFrame(
        {
            "permanent_security_id": sid,
            "symbol": symbol.upper().replace(".US", ""),
            "date": pd.to_datetime(raw["date"]).dt.normalize(),
            "open": raw["open"].astype(float),
            "high": raw["high"].astype(float),
            "low": raw["low"].astype(float),
            "close": raw["close"].astype(float),
            "volume": raw["volume"].astype(float),
        }
    )
    # Single vendor series: use as both raw and adjusted; document in config.
    for src, dst in (
        ("open", "adjusted_open"),
        ("high", "adjusted_high"),
        ("low", "adjusted_low"),
        ("close", "adjusted_close"),
        ("volume", "adjusted_volume"),
    ):
        out[dst] = out[src]
    out["split_factor"] = 1.0
    out["cash_dividend"] = 0.0
    out["exchange"] = exchange
    out["security_type"] = security_type
    out["is_delisted"] = False
    out["delisting_date"] = pd.NaT
    out["vendor_timestamp"] = None
    out["sector"] = sector
    out = out.sort_values("date").drop_duplicates(subset=["date"], keep="last")
    return ensure_schema(out)


def security_ids(df: pd.DataFrame) -> Sequence[str]:
    return list(df["permanent_security_id"].dropna().unique())
