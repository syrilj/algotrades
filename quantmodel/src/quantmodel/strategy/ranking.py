"""Deterministic candidate ranking."""

from __future__ import annotations

import pandas as pd


def rank_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    """
    Rank by:
      1. highest breakout strength
      2. highest volume multiple
      3. highest liquidity (median_dv_20)
      4. permanent_security_id ascending (tie-break)
    """
    if candidates.empty:
        return candidates.copy()
    out = candidates.copy()
    out = out.sort_values(
        by=["breakout_strength", "volume_mult", "median_dv_20", "permanent_security_id"],
        ascending=[False, False, False, True],
        kind="mergesort",  # stable deterministic
    )
    out = out.reset_index(drop=True)
    out["rank"] = out.index + 1
    return out
