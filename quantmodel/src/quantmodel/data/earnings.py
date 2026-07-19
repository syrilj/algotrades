"""Earnings blackout filters."""

from __future__ import annotations

from typing import Mapping

import pandas as pd


def earnings_blackout_mask(
    bars: pd.DataFrame,
    earnings: pd.DataFrame,
    config: Mapping,
) -> pd.Series:
    """True where a row is inside an entry blackout window around earnings."""
    e = config.get("earnings", {})
    if not e.get("enabled", False) or earnings is None or earnings.empty:
        return pd.Series(False, index=bars.index)

    before = int(e.get("entry_blackout_days_before", 7))
    after = int(e.get("entry_blackout_days_after", 1))
    blackout = pd.Series(False, index=bars.index)

    earn = earnings.copy()
    earn["earnings_date"] = pd.to_datetime(earn["earnings_date"]).dt.normalize()
    for _, erow in earn.iterrows():
        sid = erow["permanent_security_id"]
        ed = erow["earnings_date"]
        start = ed - pd.Timedelta(days=before)
        end = ed + pd.Timedelta(days=after)
        m = (bars["permanent_security_id"] == sid) & (bars["date"] >= start) & (bars["date"] <= end)
        blackout |= m
    return blackout
