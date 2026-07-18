"""Resolves squeeze alerts against realized price outcomes.

An alert fires when the phase machine transitions into a phase; this module
answers, for each configured horizon, whether price moved far enough in the
alert's direction to count as a "hit". Resolution walks a small ladder of
fallbacks so a poll gap or a market close near the horizon deadline doesn't
leave an alert permanently unresolved, while never fabricating a price when
none of the fallbacks apply (the alert simply stays pending).

``track_factor`` turns the store's aggregate hit-rate into the confidence
multiplier the engine applies to future alerts, staying neutral (1.0) until
enough alerts have resolved to be statistically meaningful.
"""

from __future__ import annotations

import datetime as dt
from typing import Callable

from .config import SqueezeConfig
from .store import SqueezeStore

# Fallback window used to decide whether the trading session has ended: if no
# snapshot lands within this many seconds after the horizon deadline, and
# `now_ts` is well past the deadline, we treat the session as closed and fall
# back to the last recorded spot of that (UTC) day.
_SESSION_END_LOOKAHEAD_SECONDS = 30 * 60
_SESSION_END_GRACE_SECONDS = 3600


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _utc_day_bounds(ts: float) -> tuple[float, float]:
    day = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).date()
    start = dt.datetime.combine(day, dt.time.min, tzinfo=dt.timezone.utc)
    end = dt.datetime.combine(day, dt.time.max, tzinfo=dt.timezone.utc)
    return start.timestamp(), end.timestamp()


def resolve_pending(
    store: SqueezeStore,
    cfg: SqueezeConfig,
    now_ts: float,
    backfill_fn: Callable[[float], float | None] | None = None,
) -> int:
    """Resolve every pending alert whose horizon deadline has arrived.

    Returns the number of outcomes inserted.
    """
    resolved = 0
    for horizon, threshold in zip(cfg.horizons_minutes, cfg.hit_thresholds_pct):
        for alert in store.alerts_without_outcome(horizon):
            if alert["transition"] == "enter_fading":
                continue  # informational only, never scored

            deadline = alert["ts"] + horizon * 60
            if now_ts < deadline:
                continue  # not due yet, stays pending

            price = _resolution_price(store, cfg, alert, deadline, now_ts, backfill_fn)
            if price is None:
                continue  # no fallback applies yet, stays pending

            sign = 1.0 if alert["direction"] == "bull" else -1.0
            ret_pct = sign * (price / alert["spot"] - 1.0) * 100.0
            hit = ret_pct >= threshold
            store.insert_outcome(alert["id"], horizon, ret_pct, hit, now_ts)
            resolved += 1
    return resolved


def _resolution_price(
    store: SqueezeStore,
    cfg: SqueezeConfig,
    alert: dict,
    deadline: float,
    now_ts: float,
    backfill_fn: Callable[[float], float | None] | None,
) -> float | None:
    # 1) A polled snapshot close to the deadline.
    found = store.spot_at_or_after(deadline, not_after=deadline + 2 * cfg.poll_seconds)
    if found is not None:
        return found[1]

    # 2) Caller-supplied backfill (e.g. a historical quote lookup).
    if backfill_fn is not None:
        bf = backfill_fn(deadline)
        if bf is not None:
            return bf

    # 3) Session-ended fallback: only once it's clear no more snapshots are
    #    coming for this alert (nothing within the lookahead window, and
    #    enough real time has passed that we're not just mid-gap).
    near = store.spot_at_or_after(deadline, not_after=deadline + _SESSION_END_LOOKAHEAD_SECONDS)
    session_ended = near is None and now_ts > deadline + _SESSION_END_GRACE_SECONDS
    if session_ended:
        day_start, day_end = _utc_day_bounds(alert["ts"])
        last = store.last_spot_of_day(day_start, day_end)
        if last is not None:
            return last[1]

    return None


def track_factor(stats: dict, cfg: SqueezeConfig) -> float:
    """Confidence multiplier derived from the resolved track record.

    Neutral (1.0) until ``min_resolved_for_track`` outcomes exist; otherwise
    ``2 * overall_hit_rate`` clamped to ``[0.5, 1.2]``.
    """
    resolved_total = stats.get("resolved_total", 0) or 0
    if resolved_total < cfg.min_resolved_for_track:
        return 1.0

    by_horizon = stats.get("by_horizon", {}) or {}
    total_n = 0
    total_hits = 0
    for horizon in cfg.horizons_minutes:
        entry = by_horizon.get(str(horizon))
        if not entry:
            continue
        total_n += entry.get("n", 0) or 0
        total_hits += entry.get("hits", 0) or 0

    if total_n == 0:
        return 1.0

    hit_rate = total_hits / total_n
    return _clamp(2.0 * hit_rate, 0.5, 1.2)
