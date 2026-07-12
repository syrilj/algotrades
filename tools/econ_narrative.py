#!/usr/bin/env python3
"""Economic / calendar / narrative features for options stack (failure-driven).

Pulls free market proxies (no paid calendar API required):
  - VIX level vs 20d MA  → fear / vol narrative
  - 10Y yield 5d change  → rates narrative
  - QQQ vs 50d MA        → growth-risk narrative
  - FOMC / CPI / NFP     → event calendar (static public dates, extendable)

Policy modes (from failure autopsy on v27 trades):
  broad     — size down on near-FOMC / high-VIX / rates / QQQ (hurt winners)
  surgical  — block ONLY fomc_day AND vix_elevated (the Dec-18 MU blowup mode)
  fomc_day  — skip FOMC decision day only
  event_vix — skip major macro day (FOMC/CPI/NFP) when VIX elevated
  off       — no narrative sizing (size_mult=1, allow always)

Usage:
  from econ_narrative import MacroNarrative
  m = MacroNarrative(start='2024-01-01', end='2026-07-15')
  m.features_on('2024-12-18', mode='surgical')
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

# Known FOMC decision days (public Fed calendar).
FOMC_DATES = pd.to_datetime(
    [
        "2024-01-31",
        "2024-03-20",
        "2024-05-01",
        "2024-06-12",
        "2024-07-31",
        "2024-09-18",
        "2024-11-07",
        "2024-12-18",
        "2025-01-29",
        "2025-03-19",
        "2025-05-07",
        "2025-06-18",
        "2025-07-30",
        "2025-09-17",
        "2025-11-05",
        "2025-12-17",
        "2026-01-28",
        "2026-03-18",
        "2026-04-29",
        "2026-06-17",
        "2026-07-29",
    ]
)

# CPI release dates (BLS, approx scheduled; extend as needed).
CPI_DATES = pd.to_datetime(
    [
        "2024-08-14",
        "2024-09-11",
        "2024-10-10",
        "2024-11-13",
        "2024-12-11",
        "2025-01-15",
        "2025-02-12",
        "2025-03-12",
        "2025-04-10",
        "2025-05-13",
        "2025-06-11",
        "2025-07-15",
        "2025-08-12",
        "2025-09-11",
        "2025-10-10",
        "2025-11-13",
        "2025-12-10",
        "2026-01-14",
        "2026-02-11",
        "2026-03-11",
        "2026-04-10",
        "2026-05-12",
        "2026-06-10",
        "2026-07-14",
    ]
)

# Nonfarm payrolls (first Friday-ish of month; public BLS schedule approx).
NFP_DATES = pd.to_datetime(
    [
        "2024-08-02",
        "2024-09-06",
        "2024-10-04",
        "2024-11-01",
        "2024-12-06",
        "2025-01-10",
        "2025-02-07",
        "2025-03-07",
        "2025-04-04",
        "2025-05-02",
        "2025-06-06",
        "2025-07-03",
        "2025-08-01",
        "2025-09-05",
        "2025-10-03",
        "2025-11-07",
        "2025-12-05",
        "2026-01-09",
        "2026-02-06",
        "2026-03-06",
        "2026-04-03",
        "2026-05-01",
        "2026-06-05",
        "2026-07-02",
    ]
)

MAJOR_EVENT_DATES = pd.DatetimeIndex(
    sorted(set(FOMC_DATES).union(set(CPI_DATES)).union(set(NFP_DATES)))
)


def _yf_close(symbol: str, start: str, end: str) -> pd.Series:
    h = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)
    if h is None or h.empty:
        return pd.Series(dtype=float)
    if isinstance(h.columns, pd.MultiIndex):
        h.columns = [c[0].lower() for c in h.columns]
    else:
        h.columns = [str(c).lower() for c in h.columns]
    s = h["close"].astype(float).copy()
    s.index = pd.to_datetime(s.index)
    if getattr(s.index, "tz", None) is not None:
        s.index = s.index.tz_localize(None)
    return s.dropna()


def _asof(series: pd.Series, ts: pd.Timestamp) -> float:
    """Safe as-of lookup; empty series → nan (fail-open for callers)."""
    if series is None or len(series) == 0:
        return float("nan")
    ts = pd.Timestamp(ts).normalize()
    try:
        idx = series.index[series.index <= ts]
    except Exception:  # noqa: BLE001
        return float("nan")
    if len(idx) == 0:
        return float("nan")
    try:
        return float(series.loc[idx[-1]])
    except Exception:  # noqa: BLE001
        return float("nan")


def _min_abs_days(dates: pd.DatetimeIndex, ts: pd.Timestamp) -> int:
    ts = pd.Timestamp(ts).normalize()
    if dates is None or len(dates) == 0:
        return 999
    try:
        deltas = np.abs((pd.DatetimeIndex(dates) - ts).days)
        return int(np.min(deltas))
    except Exception:  # noqa: BLE001
        return 999


@dataclass
class NarrativeState:
    date: str
    vix: float
    vix_ma20: float
    vix_elevated: bool
    vix_crush_risk: bool
    tnx: float
    tnx_5d: float
    rates_spike: bool
    qqq: float
    qqq_above_ma50: bool
    days_to_fomc: int
    days_to_cpi: int
    days_to_nfp: int
    days_to_major: int
    near_fomc: bool
    fomc_day: bool
    cpi_day: bool
    nfp_day: bool
    major_event_day: bool
    narrative: str
    size_mult: float
    allow_entry: bool
    policy_mode: str
    failure_mode_match: bool  # True when matches Dec-18 style blowup conditions


class MacroNarrative:
    def __init__(self, start: str = "2024-01-01", end: str = "2026-12-31"):
        self.start = start
        self.end = end
        self.vix = _yf_close("^VIX", start, end)
        self.tnx = _yf_close("^TNX", start, end)
        self.qqq = _yf_close("QQQ", start, end)
        self.vix_ma20 = self.vix.rolling(20, min_periods=10).mean()
        self.qqq_ma50 = self.qqq.rolling(50, min_periods=20).mean()
        self.tnx_5d = self.tnx.pct_change(5)
        self.vix_5d = self.vix.pct_change(5)

    def days_to_fomc(self, ts: pd.Timestamp) -> int:
        return _min_abs_days(FOMC_DATES, ts)

    def features_on(self, ts, mode: str = "surgical") -> dict[str, Any]:
        ts = pd.Timestamp(ts).normalize()
        mode = (mode or "surgical").lower()
        vix = _asof(self.vix, ts)
        vix_ma = _asof(self.vix_ma20, ts)
        tnx = _asof(self.tnx, ts)
        tnx5 = _asof(self.tnx_5d, ts)
        qqq = _asof(self.qqq, ts)
        qqq_ma = _asof(self.qqq_ma50, ts)
        vix5 = _asof(self.vix_5d, ts)
        d_fomc = self.days_to_fomc(ts)
        d_cpi = _min_abs_days(CPI_DATES, ts)
        d_nfp = _min_abs_days(NFP_DATES, ts)
        d_major = _min_abs_days(MAJOR_EVENT_DATES, ts)

        vix_elev = bool(np.isfinite(vix) and np.isfinite(vix_ma) and vix > vix_ma * 1.10)
        vix_crush = bool(vix_elev and np.isfinite(vix5) and vix5 < -0.05)
        rates_spike = bool(np.isfinite(tnx5) and tnx5 > 0.03)
        qqq_ok = bool(not np.isfinite(qqq) or not np.isfinite(qqq_ma) or qqq >= qqq_ma * 0.98)
        near = d_fomc <= 2
        fomc_day = d_fomc == 0
        cpi_day = d_cpi == 0
        nfp_day = d_nfp == 0
        major_day = d_major == 0

        # Dec-18 autopsy: FOMC day + elevated VIX (+ rates spike). Core failure mode.
        failure_mode = bool(fomc_day and vix_elev)

        tags = []
        if fomc_day or near:
            tags.append("FED_EVENT")
        if cpi_day:
            tags.append("CPI")
        if nfp_day:
            tags.append("NFP")
        if vix_elev:
            tags.append("FEAR_VOL")
        if rates_spike:
            tags.append("RATES_UP")
        if not qqq_ok:
            tags.append("GROWTH_RISK_OFF")
        if not tags:
            tags.append("RISK_ON_QUIET")
        narrative = "+".join(tags)

        size = 1.0
        allow = True

        if mode == "off":
            size, allow = 1.0, True
        elif mode == "broad":
            # Original policy — autopsy showed this cut winners (e.g. AVGO near FOMC).
            if fomc_day:
                allow, size = False, 0.0
            elif near:
                size *= 0.35
            if vix_elev:
                size *= 0.50
            if rates_spike:
                size *= 0.75
            if not qqq_ok:
                size *= 0.50
        elif mode == "fomc_day":
            if fomc_day:
                allow, size = False, 0.0
        elif mode == "event_vix":
            # Skip major calendar day only when fear is elevated.
            if major_day and vix_elev:
                allow, size = False, 0.0
            elif major_day:
                size *= 0.60
        else:
            # surgical (default): only block the proven failure mode
            if failure_mode:
                allow, size = False, 0.0
            # optional tiny soft size if rates spike + vix elev same day (not calendar)
            elif vix_elev and rates_spike and near:
                size *= 0.50

        size = float(np.clip(size, 0.0, 1.0))
        st = NarrativeState(
            date=str(ts.date()),
            vix=vix,
            vix_ma20=vix_ma,
            vix_elevated=vix_elev,
            vix_crush_risk=vix_crush,
            tnx=tnx,
            tnx_5d=tnx5 if np.isfinite(tnx5) else 0.0,
            rates_spike=rates_spike,
            qqq=qqq,
            qqq_above_ma50=qqq_ok,
            days_to_fomc=d_fomc,
            days_to_cpi=d_cpi,
            days_to_nfp=d_nfp,
            days_to_major=d_major,
            near_fomc=near,
            fomc_day=fomc_day,
            cpi_day=cpi_day,
            nfp_day=nfp_day,
            major_event_day=major_day,
            narrative=narrative,
            size_mult=size,
            allow_entry=allow and size > 0,
            policy_mode=mode,
            failure_mode_match=failure_mode,
        )
        return st.__dict__


def main():
    import argparse
    import json

    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="")
    ap.add_argument("--mode", default="surgical")
    ap.add_argument("--start", default="2024-08-01")
    ap.add_argument("--end", default="2026-07-15")
    args = ap.parse_args()
    m = MacroNarrative(args.start, args.end)
    if args.date:
        print(json.dumps(m.features_on(args.date, mode=args.mode), indent=2, default=str))
    else:
        print(json.dumps(m.features_on(pd.Timestamp.today(), mode=args.mode), indent=2, default=str))


if __name__ == "__main__":
    main()
