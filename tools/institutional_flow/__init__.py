"""`institutional_flow` — OHLCV-safe microstructure feature engineering.

This package provides a set of features that proxy institutional execution
footprints, volume-price confirmation, and order-flow toxicity using only
OHLCV bar data.  It is intentionally designed for the high-level research
pipeline: bar DataFrames in, feature DataFrames out.

Typical usage:

    from tools.institutional_flow import compute_features
    features = compute_features(bars_df, symbol="TSLA.US")

See `features.py` for the full feature list and `impact.py` for
Almgren-Chriss cost wrappers.
"""

from __future__ import annotations

from .features import compute_features
from .impact import (
    cost_for_trade,
    impact_for_notional,
    impact_per_share,
    optimal_trajectory,
    estimate_adv,
    estimate_volatility,
)

__all__ = [
    "compute_features",
    "cost_for_trade",
    "impact_for_notional",
    "impact_per_share",
    "optimal_trajectory",
    "estimate_adv",
    "estimate_volatility",
]
