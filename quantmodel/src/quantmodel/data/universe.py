"""Point-in-time universe eligibility."""

from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd


def compute_median_dollar_volume(bars: pd.DataFrame, window: int = 20) -> pd.Series:
    dv = bars["adjusted_close"] * bars["volume"]
    return dv.groupby(bars["permanent_security_id"], group_keys=False).transform(
        lambda s: s.rolling(window, min_periods=window).median()
    )


def compute_history_count(bars: pd.DataFrame) -> pd.Series:
    return bars.groupby("permanent_security_id", group_keys=False).cumcount() + 1


def annotate_universe_features(bars: pd.DataFrame) -> pd.DataFrame:
    out = bars.sort_values(["permanent_security_id", "date"]).copy()
    out["median_dv_20"] = compute_median_dollar_volume(out, 20)
    out["history_days"] = compute_history_count(out)
    return out


def eligible_mask(
    bars: pd.DataFrame,
    config: Mapping,
    *,
    asof_date: pd.Timestamp | None = None,
) -> pd.Series:
    """Boolean mask for rows eligible at their own date (vectorized)."""
    u = config["universe"]
    d = config["data"]
    min_hist = int(d.get("min_history_days", 252))
    # On short real histories, allow min of available if synthetic false and data short —
    # but keep configured value; callers may lower min_history_days in config.
    m = pd.Series(True, index=bars.index)
    m &= bars["adjusted_close"] >= float(u["min_price"])
    m &= bars["history_days"] >= min_hist
    m &= bars["median_dv_20"].fillna(0) >= float(u["min_median_dollar_volume_20d"])
    m &= ~bars["is_delisted"].fillna(False)
    if u.get("exclude_etfs", True):
        m &= bars["security_type"] != "etf"
    # Always keep benchmark rows available separately; eligibility is for trading names
    if asof_date is not None:
        m &= bars["date"] == pd.Timestamp(asof_date)
    return m


def universe_on_date(bars: pd.DataFrame, config: Mapping, asof: pd.Timestamp) -> pd.DataFrame:
    day = bars[bars["date"] == pd.Timestamp(asof)]
    if day.empty:
        return day
    mask = eligible_mask(day, config)
    # Benchmark is not traded by default unless it passes filters
    return day.loc[mask].copy()
