"""US equity trading calendar."""

from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
from typing import Iterable

import pandas as pd

try:
    import exchange_calendars as xcals
except ImportError:  # pragma: no cover
    xcals = None  # type: ignore


@lru_cache(maxsize=4)
def _us_calendar():
    if xcals is None:
        return None
    # NYSE is the standard US equity session calendar
    return xcals.get_calendar("XNYS")


def session_dates(start: date | str, end: date | str) -> pd.DatetimeIndex:
    """Return normalized trading session timestamps between start and end inclusive."""
    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end).normalize()
    cal = _us_calendar()
    if cal is not None:
        # exchange_calendars uses timezone-aware; normalize to midnight naive
        sessions = cal.sessions_in_range(start_ts, end_ts)
        return pd.DatetimeIndex(pd.to_datetime(sessions).tz_localize(None).normalize())
    # Fallback: business days Mon-Fri (no holiday calendar) — documented limitation
    return pd.bdate_range(start_ts, end_ts, freq="C")


def is_session(d: date | str) -> bool:
    ts = pd.Timestamp(d).normalize()
    cal = _us_calendar()
    if cal is not None:
        return bool(cal.is_session(ts))
    return ts.weekday() < 5


def next_session(d: date | str) -> date:
    ts = pd.Timestamp(d).normalize()
    cal = _us_calendar()
    if cal is not None:
        nxt = cal.date_to_session(ts, direction="next")
        # if ts itself is a session, advance one
        if cal.is_session(ts):
            nxt = cal.session_offset(ts, 1)
        return pd.Timestamp(nxt).date()
    # fallback
    cur = ts + pd.Timedelta(days=1)
    while cur.weekday() >= 5:
        cur += pd.Timedelta(days=1)
    return cur.date()


def align_to_sessions(dates: Iterable[date | datetime | str]) -> pd.DatetimeIndex:
    idx = pd.to_datetime(list(dates)).normalize()
    return pd.DatetimeIndex([d for d in idx if is_session(d.date())])
