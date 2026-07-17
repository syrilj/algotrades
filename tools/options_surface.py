#!/usr/bin/env python3
"""Option surface snapshot: ATM IV, term slope, skew, and live flow pressure.

Live path uses yfinance chains. Research path can inject a prebuilt surface
dict (tests / offline). No silent empty surface — always returns data_quality.

Also captures put/call volume+OI and short-horizon spot return so the desk can
warn on patterns like "puts stacking while stock climbs".
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

try:
    import yfinance as yf
except ImportError:  # pragma: no cover
    yf = None  # type: ignore


def _jsonable(obj):
    """Convert NaN/Inf to None for strict JSON (desk parse safety)."""
    import math
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj



def _mid(bid: Any, ask: Any, last: Any) -> float:
    try:
        b, a = float(bid or 0), float(ask or 0)
        if b > 0 and a > 0:
            return 0.5 * (b + a)
        return float(last or 0)
    except Exception:
        return 0.0


def _sum_col(frame: pd.DataFrame, col: str) -> float:
    if frame is None or frame.empty or col not in frame.columns:
        return 0.0
    return float(pd.to_numeric(frame[col], errors="coerce").fillna(0.0).sum())


def _atm_iv_from_frame(opts: pd.DataFrame, spot: float) -> Tuple[float, float]:
    """Return (atm_iv, atm_strike) from a call/put frame with strike + IV + mid."""
    if opts is None or opts.empty or spot <= 0:
        return float("nan"), float("nan")
    df = opts.copy()
    if "impliedVolatility" in df.columns:
        df["iv"] = pd.to_numeric(df["impliedVolatility"], errors="coerce")
    elif "iv" in df.columns:
        df["iv"] = pd.to_numeric(df["iv"], errors="coerce")
    else:
        return float("nan"), float("nan")
    if "mid" not in df.columns:
        if "bid" in df.columns and "ask" in df.columns:
            b = pd.to_numeric(df["bid"], errors="coerce").fillna(0.0)
            a = pd.to_numeric(df["ask"], errors="coerce").fillna(0.0)
            last = (
                pd.to_numeric(df["lastPrice"], errors="coerce").fillna(0.0)
                if "lastPrice" in df.columns
                else pd.Series(0.0, index=df.index)
            )
            df["mid"] = np.where((b > 0) & (a > 0), 0.5 * (b + a), last)
        elif "lastPrice" in df.columns:
            df["mid"] = pd.to_numeric(df["lastPrice"], errors="coerce").fillna(0.0)
        else:
            df["mid"] = 1.0  # allow IV-only frames in tests
    df = df[(df["iv"] > 0.01) & (df["iv"] < 5.0) & (df["mid"] > 0)].copy()
    if df.empty:
        return float("nan"), float("nan")
    df["abs_mny"] = (df["strike"].astype(float) - spot).abs()
    row = df.sort_values(["abs_mny"]).iloc[0]
    return float(row["iv"]), float(row["strike"])


def _skew_proxy(calls: pd.DataFrame, puts: pd.DataFrame, spot: float) -> float:
    """Rough wing skew: OTM put IV − OTM call IV at ~0.9/1.1 moneyness."""
    if spot <= 0:
        return float("nan")
    put_k = spot * 0.90
    call_k = spot * 1.10

    def _iv_near(frame: pd.DataFrame, k: float) -> float:
        if frame is None or frame.empty:
            return float("nan")
        df = frame.copy()
        col = "impliedVolatility" if "impliedVolatility" in df.columns else "iv"
        if col not in df.columns:
            return float("nan")
        df["iv"] = pd.to_numeric(df[col], errors="coerce")
        df = df[df["iv"] > 0.01]
        if df.empty:
            return float("nan")
        df["d"] = (df["strike"].astype(float) - k).abs()
        return float(df.sort_values("d").iloc[0]["iv"])

    piv = _iv_near(puts, put_k)
    civ = _iv_near(calls, call_k)
    if math.isnan(piv) or math.isnan(civ):
        return float("nan")
    return piv - civ


def surface_from_chains(
    spot: float,
    expiries: Sequence[Tuple[str, int, pd.DataFrame, pd.DataFrame]],
    *,
    spot_ret_5d: float = float("nan"),
    spot_ret_1d: float = float("nan"),
) -> Dict[str, Any]:
    """Build surface metrics from a list of (expiry, dte, calls, puts)."""
    rows: List[Dict[str, Any]] = []
    call_vol = put_vol = call_oi = put_oi = 0.0

    for exp, dte, calls, puts in expiries:
        civ, cstrike = _atm_iv_from_frame(calls, spot)
        piv, pstrike = _atm_iv_from_frame(puts, spot)
        ivs = [x for x in (civ, piv) if not math.isnan(x)]
        atm = float(np.mean(ivs)) if ivs else float("nan")
        skew = _skew_proxy(calls, puts, spot)
        cv = _sum_col(calls, "volume")
        pv = _sum_col(puts, "volume")
        co = _sum_col(calls, "openInterest")
        po = _sum_col(puts, "openInterest")
        call_vol += cv
        put_vol += pv
        call_oi += co
        put_oi += po
        rows.append(
            {
                "expiry": exp,
                "dte": int(dte),
                "atm_iv": atm,
                "atm_call_iv": civ,
                "atm_put_iv": piv,
                "atm_strike": cstrike if not math.isnan(cstrike) else pstrike,
                "skew_proxy": skew,
                "call_volume": cv,
                "put_volume": pv,
                "call_oi": co,
                "put_oi": po,
            }
        )

    rows = [r for r in rows if not math.isnan(r["atm_iv"])]
    rows.sort(key=lambda r: r["dte"])

    if not rows:
        return {
            "ok": False,
            "data_quality": "degraded",
            "spot": float(spot),
            "tenors": [],
            "atm_iv": float("nan"),
            "near_dte": None,
            "next_dte": None,
            "term_slope": float("nan"),
            "skew_25d": float("nan"),
            "call_volume": 0.0,
            "put_volume": 0.0,
            "call_oi": 0.0,
            "put_oi": 0.0,
            "put_call_vol_ratio": float("nan"),
            "put_call_oi_ratio": float("nan"),
            "spot_ret_1d": float(spot_ret_1d) if not math.isnan(spot_ret_1d) else float("nan"),
            "spot_ret_5d": float(spot_ret_5d) if not math.isnan(spot_ret_5d) else float("nan"),
            "error": "no valid IV tenors",
        }

    near = rows[0]
    nxt = rows[1] if len(rows) > 1 else None
    term_slope = float("nan")
    if nxt is not None and nxt["dte"] > near["dte"]:
        term_slope = (nxt["atm_iv"] - near["atm_iv"]) * (30.0 / (nxt["dte"] - near["dte"]))

    pc_vol = put_vol / call_vol if call_vol > 0 else float("nan")
    pc_oi = put_oi / call_oi if call_oi > 0 else float("nan")

    quality = "ok" if len(rows) >= 2 else "partial"

    return {
        "ok": True,
        "data_quality": quality,
        "spot": float(spot),
        "tenors": rows,
        "atm_iv": float(near["atm_iv"]),
        "near_dte": int(near["dte"]),
        "next_dte": int(nxt["dte"]) if nxt else None,
        "term_slope": float(term_slope) if not math.isnan(term_slope) else float("nan"),
        "skew_25d": float(near["skew_proxy"]) if not math.isnan(near.get("skew_proxy", float("nan"))) else float("nan"),
        "call_volume": float(call_vol),
        "put_volume": float(put_vol),
        "call_oi": float(call_oi),
        "put_oi": float(put_oi),
        "put_call_vol_ratio": float(pc_vol) if not math.isnan(pc_vol) else float("nan"),
        "put_call_oi_ratio": float(pc_oi) if not math.isnan(pc_oi) else float("nan"),
        "spot_ret_1d": float(spot_ret_1d) if not math.isnan(spot_ret_1d) else float("nan"),
        "spot_ret_5d": float(spot_ret_5d) if not math.isnan(spot_ret_5d) else float("nan"),
        "asof_utc": datetime.now(timezone.utc).isoformat(),
    }


def _sum_col(frame: pd.DataFrame, col: str) -> float:
    if frame is None or frame.empty or col not in frame.columns:
        return 0.0
    return float(pd.to_numeric(frame[col], errors="coerce").fillna(0.0).sum())


def fetch_live_surface(
    symbol: str,
    min_dte: int = 7,
    max_dte: int = 90,
    max_expiries: int = 4,
) -> Dict[str, Any]:
    """Live yfinance surface snapshot with put/call flow and spot momentum."""
    sym = symbol.upper().replace(".US", "")
    if yf is None:
        return {
            "ok": False,
            "symbol": sym,
            "data_quality": "degraded",
            "error": "yfinance not installed",
            "atm_iv": float("nan"),
            "term_slope": float("nan"),
            "skew_25d": float("nan"),
            "call_volume": 0.0,
            "put_volume": 0.0,
            "call_oi": 0.0,
            "put_oi": 0.0,
            "put_call_vol_ratio": float("nan"),
            "put_call_oi_ratio": float("nan"),
            "spot_ret_1d": float("nan"),
            "spot_ret_5d": float("nan"),
        }

    t = yf.Ticker(sym)
    try:
        hist = t.history(period="10d")
    except Exception as e:
        return {
            "ok": False,
            "symbol": sym,
            "data_quality": "degraded",
            "error": f"history failed: {e}",
            "atm_iv": float("nan"),
            "term_slope": float("nan"),
            "skew_25d": float("nan"),
            "call_volume": 0.0,
            "put_volume": 0.0,
            "call_oi": 0.0,
            "put_oi": 0.0,
            "put_call_vol_ratio": float("nan"),
            "put_call_oi_ratio": float("nan"),
            "spot_ret_1d": float("nan"),
            "spot_ret_5d": float("nan"),
        }
    if hist is None or hist.empty:
        return {
            "ok": False,
            "symbol": sym,
            "data_quality": "degraded",
            "error": "no spot",
            "atm_iv": float("nan"),
            "term_slope": float("nan"),
            "skew_25d": float("nan"),
            "call_volume": 0.0,
            "put_volume": 0.0,
            "call_oi": 0.0,
            "put_oi": 0.0,
            "put_call_vol_ratio": float("nan"),
            "put_call_oi_ratio": float("nan"),
            "spot_ret_1d": float("nan"),
            "spot_ret_5d": float("nan"),
        }

    closes = hist["Close"].astype(float)
    spot = float(closes.iloc[-1])
    spot_ret_1d = float("nan")
    spot_ret_5d = float("nan")
    if len(closes) >= 2 and closes.iloc[-2] > 0:
        spot_ret_1d = float(closes.iloc[-1] / closes.iloc[-2] - 1.0)
    if len(closes) >= 6 and closes.iloc[-6] > 0:
        spot_ret_5d = float(closes.iloc[-1] / closes.iloc[-6] - 1.0)
    elif len(closes) >= 2 and closes.iloc[0] > 0:
        spot_ret_5d = float(closes.iloc[-1] / closes.iloc[0] - 1.0)

    try:
        expiries = list(t.options or [])
    except Exception as e:
        return {
            "ok": False,
            "symbol": sym,
            "data_quality": "degraded",
            "error": f"no expiries: {e}",
            "spot": spot,
            "atm_iv": float("nan"),
            "term_slope": float("nan"),
            "skew_25d": float("nan"),
            "call_volume": 0.0,
            "put_volume": 0.0,
            "call_oi": 0.0,
            "put_oi": 0.0,
            "put_call_vol_ratio": float("nan"),
            "put_call_oi_ratio": float("nan"),
            "spot_ret_1d": spot_ret_1d,
            "spot_ret_5d": spot_ret_5d,
        }

    now = pd.Timestamp.utcnow().tz_localize(None).normalize()
    picked: List[Tuple[str, int, pd.DataFrame, pd.DataFrame]] = []
    for exp in expiries:
        dte = (pd.Timestamp(exp) - now).days
        if dte < min_dte or dte > max_dte:
            continue
        try:
            chain = t.option_chain(exp)
            picked.append((exp, int(dte), chain.calls.copy(), chain.puts.copy()))
        except Exception:
            continue
        if len(picked) >= max_expiries:
            break

    surface = surface_from_chains(
        spot,
        picked,
        spot_ret_1d=spot_ret_1d,
        spot_ret_5d=spot_ret_5d,
    )
    surface["symbol"] = sym
    if not surface.get("ok"):
        surface["error"] = surface.get("error") or "chain empty after filters"
    return surface


def main(argv: Optional[list] = None) -> int:
    import argparse
    import json

    p = argparse.ArgumentParser(description="Live options surface snapshot")
    p.add_argument("--symbol", default="SPY")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    row = fetch_live_surface(args.symbol)
    print(json.dumps(_jsonable(row), default=str))
    return 0 if row.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
