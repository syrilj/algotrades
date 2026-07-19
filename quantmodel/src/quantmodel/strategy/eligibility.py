"""Eligibility reason helpers."""

from __future__ import annotations

from typing import Mapping

import pandas as pd

from quantmodel.data.universe import eligible_mask


def eligibility_table(bars: pd.DataFrame, config: Mapping) -> pd.DataFrame:
    m = eligible_mask(bars, config)
    return bars.assign(eligibility_pass=m)
