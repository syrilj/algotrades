"""Corporate-action adjustment helpers."""

from __future__ import annotations

import pandas as pd


def apply_split_to_position_shares(shares: int, split_factor: float) -> int:
    """Adjust share count for a split (e.g. 2.0 => double shares)."""
    if split_factor <= 0:
        raise ValueError(f"Invalid split_factor {split_factor}")
    return int(round(shares * split_factor))


def apply_split_to_price(price: float, split_factor: float) -> float:
    if split_factor <= 0:
        raise ValueError(f"Invalid split_factor {split_factor}")
    return price / split_factor


def sessions_with_splits(bars: pd.DataFrame) -> pd.DataFrame:
    return bars.loc[bars["split_factor"].fillna(1.0) != 1.0].copy()
