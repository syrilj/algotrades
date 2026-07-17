from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from .contracts import (
    DataFreshness,
    Horizon,
    Instrument,
    InstrumentCategory,
    InstrumentClassification,
    Opportunity,
    RankedOpportunity,
    require_utc,
)


_DEFAULT_THRESHOLD = timedelta(minutes=15)


_SWING_CATEGORIES = {
    InstrumentClassification.CONTEXT_ONLY,
    InstrumentClassification.UNSUPPORTED,
}


_INTRADAY_THRESHOLD = 0.05
_LIQUIDITY_THRESHOLD = 0.5
_ACTIVITY_THRESHOLD = 0.5


def evaluate_freshness(
    instrument: Instrument,
    market_asof: datetime,
    computed_at: datetime,
    thresholds: Optional[Dict[InstrumentCategory, timedelta]] = None,
) -> DataFreshness:
    require_utc(market_asof, "market_asof")
    require_utc(computed_at, "computed_at")
    age = computed_at - market_asof
    future_timestamp = age < -timedelta(minutes=5)
    if age < timedelta(0):
        age = timedelta(0)
    threshold = thresholds.get(instrument.category, _DEFAULT_THRESHOLD) if thresholds else _DEFAULT_THRESHOLD
    is_stale = future_timestamp or age > threshold
    return DataFreshness(
        category=instrument.category,
        market_asof=market_asof,
        computed_at=computed_at,
        age=age,
        threshold=threshold,
        is_stale=is_stale,
    )


def classify_horizon(
    instrument: Instrument,
    liquidity: float,
    activity: float,
    volatility: float,
    session_active: bool,
    freshness: DataFreshness,
) -> Horizon:
    if instrument.classification in _SWING_CATEGORIES:
        return Horizon.SWING
    if not session_active:
        return Horizon.SWING
    if freshness.is_stale:
        return Horizon.SWING
    if liquidity < _LIQUIDITY_THRESHOLD or activity < _ACTIVITY_THRESHOLD:
        return Horizon.SWING
    if volatility > _INTRADAY_THRESHOLD:
        return Horizon.SWING
    return Horizon.INTRADAY


def rank_opportunities(rows: List[Opportunity]) -> List[RankedOpportunity]:
    accepted = [
        row
        for row in rows
        if row.actionable
        and row.instrument.classification == InstrumentClassification.TRADABLE
        and not row.freshness.is_stale
    ]

    cohorts: Dict[Tuple[str, Horizon], List[Opportunity]] = defaultdict(list)
    for row in accepted:
        cohorts[(row.instrument.asset_class, row.horizon)].append(row)

    cohort_metadata: Dict[Tuple[str, Horizon], Dict[str, int]] = {}
    for key, group in cohorts.items():
        sorted_group = sorted(group, key=lambda row: (-row.score, row.instrument.symbol))
        scores = [row.score for row in sorted_group]
        min_score = min(scores)
        max_score = max(scores)
        cohort_metadata[key] = {
            "sorted": sorted_group,
            "min_score": min_score,
            "max_score": max_score,
        }

    all_scores = [row.score for row in accepted]
    global_min = min(all_scores) if all_scores else 0.0
    global_max = max(all_scores) if all_scores else 0.0
    global_range = global_max - global_min

    ranked: List[RankedOpportunity] = []
    for key, meta in cohort_metadata.items():
        sorted_group = meta["sorted"]
        min_score = meta["min_score"]
        max_score = meta["max_score"]
        cohort_range = max_score - min_score
        for cohort_rank, row in enumerate(sorted_group, start=1):
            if cohort_range > 0:
                cohort_score = (row.score - min_score) / cohort_range
            else:
                cohort_score = 1.0
            if global_range > 0:
                priority = (row.score - global_min) / global_range
            else:
                priority = 1.0
            ranked.append(
                RankedOpportunity(
                    opportunity=row,
                    cohort_rank=cohort_rank,
                    cohort_size=len(sorted_group),
                    cohort_score=cohort_score,
                    priority=priority,
                )
            )

    ranked.sort(key=lambda r: (-r.priority, -r.opportunity.score, r.opportunity.instrument.symbol))
    return ranked
