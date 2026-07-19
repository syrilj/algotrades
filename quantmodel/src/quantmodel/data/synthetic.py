"""Deterministic synthetic multi-asset universe for engine correctness tests."""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from quantmodel.data.calendar import session_dates
from quantmodel.data.schema import ensure_schema
from quantmodel.hashing import sha256_text


def generate_synthetic_universe(
    *,
    start: str = "2018-01-01",
    end: str = "2024-12-31",
    seed: int = 42,
    n_stocks: int = 8,
) -> dict[str, Any]:
    """Return bars frame, earnings table, metadata, and data manifest hash."""
    rng = np.random.default_rng(seed)
    sessions = session_dates(start, end)
    if len(sessions) < 300:
        raise ValueError("Synthetic range too short for SMA200 + history filters")

    n = len(sessions)
    # Benchmark: mostly bullish so regime filter is usually ON (trend research default)
    spy_rets = rng.normal(0.00045, 0.008, size=n)
    # one bear patch so regime filter actually turns off sometimes
    bear0, bear1 = int(n * 0.42), int(n * 0.48)
    spy_rets[bear0:bear1] = rng.normal(-0.0012, 0.012, size=bear1 - bear0)
    spy_close = 250 * np.cumprod(1 + spy_rets)
    frames: list[pd.DataFrame] = []

    # SPY benchmark
    frames.append(
        _make_bars(
            "SPY",
            "SID_SPY",
            sessions,
            spy_close,
            volume_base=8e7,
            rng=rng,
            sector="ETF",
            security_type="etf",
        )
    )

    # Trend stocks: plant multi-week breakout legs so a Donchian system can express edge
    for i in range(n_stocks):
        sym = f"T{i:02d}"
        sid = f"SID_{sym}"
        if i % 3 == 0:
            base_drift, base_vol = 0.00055, 0.014
        elif i % 3 == 1:
            base_drift, base_vol = 0.00025, 0.016
        else:
            base_drift, base_vol = 0.00005, 0.018
        rets = rng.normal(base_drift, base_vol, size=n)
        # 3–4 sustained trend legs per name (breakout + follow-through)
        for k, frac in enumerate((0.22, 0.38, 0.55, 0.72)):
            start_i = int(n * frac) + i * 3 + k
            if start_i + 45 >= n:
                continue
            # compression then thrust
            rets[start_i : start_i + 8] = rng.normal(0.0, base_vol * 0.5, size=8)
            rets[start_i + 8 : start_i + 12] += 0.012 + 0.002 * (i % 3)
            rets[start_i + 12 : start_i + 40] += rng.normal(0.0035, base_vol * 0.4, size=28)
        close = 30 + i * 8 + 25 * np.cumprod(1 + rets)
        vol_base = 2.5e6 * (1 + 0.15 * i)
        fr = _make_bars(
            sym,
            sid,
            sessions,
            close,
            volume_base=vol_base,
            rng=rng,
            sector=_sector(i),
            surge_centers=[int(n * f) + i * 3 for f in (0.22, 0.38, 0.55, 0.72)],
        )
        # Corporate action: 2-for-1 split mid-way on stock 0
        if i == 0:
            split_i = len(sessions) // 3
            fr.loc[split_i, "split_factor"] = 2.0
        # Delist stock 1 near the end
        if i == 1:
            delist_i = len(sessions) - 40
            fr.loc[delist_i:, "is_delisted"] = True
            fr["delisting_date"] = pd.to_datetime(fr["delisting_date"])
            fr.loc[delist_i, "delisting_date"] = sessions[delist_i]
            fr = fr.iloc[: delist_i + 1].copy()
        frames.append(fr)

    bars = pd.concat(frames, ignore_index=True)
    bars = ensure_schema(bars)

    # Earnings blackouts for T00 quarterly-ish
    earnings_rows = []
    t0_dates = sessions[::63]
    for d in t0_dates:
        earnings_rows.append(
            {
                "permanent_security_id": "SID_T00",
                "symbol": "T00",
                "earnings_date": d.date(),
            }
        )
    earnings = pd.DataFrame(earnings_rows)

    meta = {
        "vendor": "synthetic",
        "start": str(start),
        "end": str(end),
        "seed": seed,
        "n_stocks": n_stocks,
        "n_bars": int(len(bars)),
        "survivorship_bias": False,
        "symbols": sorted(bars["symbol"].unique().tolist()),
    }
    manifest_hash = sha256_text(str(meta) + str(len(bars)) + str(seed))
    meta["data_manifest_hash"] = manifest_hash
    return {"bars": bars, "earnings": earnings, "metadata": meta}


def _sector(i: int) -> str:
    sectors = ["TECH", "FIN", "HLTH", "IND", "CONS", "ENRG"]
    return sectors[i % len(sectors)]


def _make_bars(
    symbol: str,
    sid: str,
    sessions: pd.DatetimeIndex,
    close: np.ndarray,
    *,
    volume_base: float,
    rng: np.random.Generator,
    sector: str,
    security_type: str = "common_stock",
    surge_centers: list[int] | None = None,
) -> pd.DataFrame:
    close = np.asarray(close, dtype=float)
    n = len(sessions)
    # reconstruct rough OHLC from close path
    noise = rng.uniform(0.002, 0.012, size=n)
    open_ = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, 0.001, n))
    high = np.maximum(open_, close) * (1 + noise)
    low = np.minimum(open_, close) * (1 - noise)
    volume = volume_base * rng.uniform(0.6, 1.4, size=n)
    # occasional volume surges + planted breakout surges
    surge = rng.random(n) < 0.03
    volume[surge] *= rng.uniform(2.0, 4.0, size=int(surge.sum()))
    if surge_centers:
        for c in surge_centers:
            if 0 <= c < n:
                lo, hi = max(0, c + 6), min(n, c + 16)
                volume[lo:hi] *= rng.uniform(2.2, 3.5, size=hi - lo)

    df = pd.DataFrame(
        {
            "permanent_security_id": sid,
            "symbol": symbol,
            "date": sessions,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "adjusted_open": open_,
            "adjusted_high": high,
            "adjusted_low": low,
            "adjusted_close": close,
            "adjusted_volume": volume,
            "split_factor": 1.0,
            "cash_dividend": 0.0,
            "exchange": "NYSE",
            "security_type": security_type,
            "is_delisted": False,
            "delisting_date": pd.NaT,
            "vendor_timestamp": None,
            "sector": sector,
        }
    )
    return df
