#!/usr/bin/env python3
"""Sector relative strength + weekly watchlist (research W5).

Computes RS of sector ETFs vs SPY and ranks names for next-week focus.
No overfit claims — descriptive rotation scan only.

Usage:
  .venv/bin/python tools/sector_watchlist.py
  .venv/bin/python tools/sector_watchlist.py --json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

# Sector ETFs + example names that trade like those books
SECTORS: dict[str, dict[str, Any]] = {
    "XLK": {
        "name": "Tech",
        "names": ["NVDA", "AAPL", "MSFT", "AVGO", "AMD", "META", "GOOGL"],
    },
    "XLF": {"name": "Financials", "names": ["JPM", "GS", "HOOD", "BAC"]},
    "XLE": {"name": "Energy", "names": ["XOM", "CVX", "OXY"]},
    "XLV": {"name": "Health", "names": ["UNH", "LLY", "JNJ"]},
    "XLY": {"name": "Discretionary", "names": ["AMZN", "TSLA", "HD"]},
    "XLI": {"name": "Industrials", "names": ["CAT", "GE", "HON"]},
    "XLP": {"name": "Staples", "names": ["PG", "KO", "WMT"]},
    "XLU": {"name": "Utilities", "names": ["NEE", "DUK"]},
    "XLRE": {"name": "RealEstate", "names": ["AMT", "PLD"]},
    "XLB": {"name": "Materials", "names": ["LIN", "FCX"]},
    "XLC": {"name": "Comm", "names": ["META", "NFLX", "DIS"]},
    "SMH": {"name": "Semis", "names": ["NVDA", "AVGO", "AMD", "MU", "TSM", "ARM"]},
    "ARKK": {"name": "Innovation", "names": ["TSLA", "COIN", "ROKU", "HOOD"]},
    "BOTZ": {"name": "Robotics/AI", "names": ["NVDA", "ISRG", "PATH"]},
    "HACK": {"name": "Cyber", "names": ["CRWD", "PANW", "ZS"]},
}


def _dl(tickers: list[str], period: str = "6mo") -> pd.DataFrame:
    h = yf.download(
        tickers,
        period=period,
        group_by="ticker",
        auto_adjust=True,
        progress=False,
        threads=True,
    )
    if h is None or h.empty:
        return pd.DataFrame()
    closes = {}
    if len(tickers) == 1:
        t = tickers[0]
        if "Close" in h.columns:
            closes[t] = h["Close"].astype(float)
        elif isinstance(h.columns, pd.MultiIndex):
            closes[t] = h.xs("Close", axis=1, level=-1).iloc[:, 0].astype(float)
    else:
        if isinstance(h.columns, pd.MultiIndex):
            for t in tickers:
                try:
                    if t in h.columns.get_level_values(0):
                        closes[t] = h[t]["Close"].astype(float)
                except Exception:
                    continue
        else:
            closes[tickers[0]] = h["Close"].astype(float)
    out = pd.DataFrame(closes).dropna(how="all")
    if getattr(out.index, "tz", None) is not None:
        out.index = out.index.tz_localize(None)
    return out


def rs_score(px: pd.Series, bench: pd.Series, look: int = 21) -> float:
    """Relative strength: name ret − SPY ret over look days."""
    a = px.dropna()
    b = bench.reindex(a.index).ffill().dropna()
    a = a.reindex(b.index).ffill()
    if len(a) < look + 2 or len(b) < look + 2:
        return float("nan")
    ra = float(a.iloc[-1] / a.iloc[-look] - 1.0)
    rb = float(b.iloc[-1] / b.iloc[-look] - 1.0)
    return ra - rb


def build_watchlist(
    period: str = "6mo",
    lookbacks: tuple[int, ...] = (5, 21, 63),
) -> dict[str, Any]:
    sector_tickers = list(SECTORS.keys()) + ["SPY"]
    closes = _dl(sector_tickers, period=period)
    if closes.empty or "SPY" not in closes.columns:
        return {"ok": False, "error": "failed to download sector ETFs / SPY"}

    spy = closes["SPY"]
    sector_rows = []
    for etf, meta in SECTORS.items():
        if etf not in closes.columns:
            continue
        row = {
            "etf": etf,
            "sector": meta["name"],
            "names": meta["names"],
        }
        for lb in lookbacks:
            row[f"rs_{lb}d"] = rs_score(closes[etf], spy, lb)
            row[f"ret_{lb}d"] = float(
                closes[etf].iloc[-1] / closes[etf].iloc[-min(lb, len(closes[etf]) - 1)] - 1.0
            )
        # composite: favor 5d + 21d rotation
        r5 = row.get("rs_5d", np.nan)
        r21 = row.get("rs_21d", np.nan)
        row["score"] = float(
            np.nanmean([r5 * 0.45, r21 * 0.40, row.get("rs_63d", np.nan) * 0.15])
        )
        sector_rows.append(row)

    sector_rows.sort(key=lambda x: x.get("score", -9), reverse=True)
    leaders = sector_rows[:4]
    laggards = list(reversed(sector_rows[-3:])) if len(sector_rows) >= 3 else []

    # Expand names from leading sectors + score vs SPY
    focus_names = []
    seen = set()
    for s in leaders:
        for n in s["names"]:
            if n not in seen:
                seen.add(n)
                focus_names.append(n)

    # Also include high-beta bag always
    for n in ["TSLA", "MSTR", "IONQ", "HOOD", "MU"]:
        if n not in seen:
            seen.add(n)
            focus_names.append(n)

    name_px = _dl(list(seen) + ["SPY"], period=period) if seen else pd.DataFrame()
    name_rows = []
    if not name_px.empty and "SPY" in name_px.columns:
        spy2 = name_px["SPY"]
        for n in focus_names:
            if n not in name_px.columns:
                continue
            r21 = rs_score(name_px[n], spy2, 21)
            r5 = rs_score(name_px[n], spy2, 5)
            name_rows.append(
                {
                    "symbol": n,
                    "rs_5d": r5,
                    "rs_21d": r21,
                    "score": float(np.nanmean([r5 * 0.5, r21 * 0.5])),
                    "sector_hint": next(
                        (s["sector"] for s in sector_rows if n in s["names"]), "Other"
                    ),
                }
            )
        name_rows.sort(key=lambda x: x.get("score", -9), reverse=True)

    # Narrative for next week
    top = leaders[0] if leaders else None
    bot = laggards[0] if laggards else None
    narrative = []
    if top and np.isfinite(top.get("score", np.nan)):
        narrative.append(
            f"Leadership: {top['sector']} ({top['etf']}) RS21={top.get('rs_21d', 0)*100:+.1f}% vs SPY"
        )
    if bot and np.isfinite(bot.get("score", np.nan)):
        narrative.append(
            f"Laggard: {bot['sector']} ({bot['etf']}) RS21={bot.get('rs_21d', 0)*100:+.1f}% vs SPY"
        )
    narrative.append(
        "Bias: prefer VPA CALL setups in leading sectors; puts/weakness fades more in laggards (research, not 80% WR)."
    )

    return {
        "ok": True,
        "asof": datetime.now(timezone.utc).isoformat(),
        "benchmark": "SPY",
        "lookbacks_days": list(lookbacks),
        "sectors_ranked": sector_rows,
        "leaders": leaders,
        "laggards": laggards,
        "watch_names": name_rows[:20],
        "narrative": narrative,
        "disclaimer": "Sector RS is descriptive rotation research — not a validated 80% WR system.",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--period", default="6mo")
    args = ap.parse_args()
    out = build_watchlist(period=args.period)
    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        if not out.get("ok"):
            print("ERROR", out.get("error"))
            return 1
        print("=== SECTOR RS vs SPY ===")
        for s in out["sectors_ranked"][:8]:
            print(
                f"  {s['etf']:5} {s['sector']:14} score={s['score']*100:+5.1f}% "
                f"rs5={s.get('rs_5d',0)*100:+5.1f}% rs21={s.get('rs_21d',0)*100:+5.1f}%"
            )
        print("\n=== WATCH NAMES ===")
        for n in out["watch_names"][:12]:
            print(
                f"  {n['symbol']:6} {n['sector_hint']:12} score={n['score']*100:+5.1f}% "
                f"rs5={n.get('rs_5d',0)*100:+5.1f}% rs21={n.get('rs_21d',0)*100:+5.1f}%"
            )
        print("\n".join(out["narrative"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
