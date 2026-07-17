#!/usr/bin/env python3
"""Same-day unusual options activity flags from chain aggregates.

Not a full OPRA time-and-sales / sweep tape. Scores listed contracts using
volume vs open interest, premium/notional, moneyness, and DTE — InsiderFinance
flow-style *flags*, not proprietary prints.

Usage:
  .venv/bin/python tools/options_unusual_flow.py --symbol TSLA --json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

try:
    import yfinance as yf
except ImportError:  # pragma: no cover
    yf = None  # type: ignore


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(obj, (np.integer,)):
        return int(obj)
    return obj


def _mid(bid: Any, ask: Any, last: Any) -> float:
    try:
        b, a = float(bid or 0), float(ask or 0)
        if b > 0 and a > 0:
            return 0.5 * (b + a)
        return float(last or 0)
    except Exception:
        return 0.0


def _num(series: pd.Series, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(default)


def score_contract_row(
    *,
    symbol: str,
    expiry: str,
    dte: int,
    right: str,  # C | P
    strike: float,
    spot: float,
    volume: float,
    open_interest: float,
    mid: float,
    iv: float | None = None,
    min_volume: float = 100.0,
    min_premium: float = 25_000.0,
    vol_oi_unusual: float = 2.0,
    otm_pct_min: float = 0.03,
    short_dte_max: int = 14,
) -> Optional[Dict[str, Any]]:
    """Return a flagged row if the contract looks unusual, else None.

    Pure helper for unit tests — no network.
    """
    if spot <= 0 or strike <= 0:
        return None
    volume = float(volume or 0)
    oi = float(open_interest or 0)
    mid = float(mid or 0)
    if volume < min_volume and mid * volume * 100 < min_premium:
        return None

    premium = mid * volume * 100.0
    vol_oi = volume / oi if oi > 0 else (volume if volume > 0 else 0.0)
    moneyness = (strike - spot) / spot
    abs_mny = abs(moneyness)
    right_u = right.upper()[:1]
    is_call = right_u == "C"
    is_otm = (is_call and strike > spot * (1 + otm_pct_min * 0.5)) or (
        not is_call and strike < spot * (1 - otm_pct_min * 0.5)
    )
    deep_otm = abs_mny >= otm_pct_min
    short_dte = 0 <= dte <= short_dte_max

    reasons: List[str] = []
    score = 0.0

    if oi > 0 and vol_oi >= vol_oi_unusual and volume >= min_volume:
        score += min(40.0, 15.0 + 10.0 * math.log10(max(vol_oi, 1.0)))
        reasons.append(f"vol_vs_oi:{vol_oi:.1f}x")
    elif oi <= 0 and volume >= min_volume * 2:
        score += 25.0
        reasons.append("new_print_no_oi")

    if premium >= min_premium:
        score += min(35.0, 10.0 + math.log10(max(premium, 1.0)) * 4.0)
        reasons.append(f"premium:${premium:,.0f}")

    if is_otm and deep_otm and volume >= min_volume:
        score += 15.0 if short_dte else 8.0
        side = "otm_call" if is_call else "otm_put"
        reasons.append(f"{side}:{abs_mny * 100:.1f}pct")

    if short_dte and volume >= min_volume and (vol_oi >= 1.0 or premium >= min_premium * 0.5):
        score += 12.0
        reasons.append(f"short_dte:{dte}d")

    # Quiet ATM churn is not unusual — require real size pressure, not just mid*vol.
    if abs_mny < 0.015:
        hot_atm = (oi > 0 and vol_oi >= vol_oi_unusual and volume >= min_volume) or (
            volume >= min_volume * 3 and premium >= min_premium * 2
        )
        if not hot_atm:
            return None

    if score < 28.0 or not reasons:
        return None

    severity = "high" if score >= 55 else ("watch" if score >= 40 else "info")
    return {
        "symbol": symbol.upper().replace(".US", ""),
        "expiry": expiry,
        "dte": int(dte),
        "right": "C" if is_call else "P",
        "strike": float(strike),
        "spot": float(spot),
        "volume": float(volume),
        "open_interest": float(oi) if oi > 0 else 0.0,
        "vol_oi": float(vol_oi) if oi > 0 else None,
        "mid": float(mid) if mid > 0 else None,
        "premium": float(premium) if premium > 0 else None,
        "iv": float(iv) if iv is not None and math.isfinite(iv) else None,
        "moneyness_pct": float(moneyness * 100.0),
        "score": round(float(score), 1),
        "severity": severity,
        "reasons": reasons,
        "reason": "; ".join(reasons),
        "unusual": True,
        "methodology": "chain_aggregate_proxy",
    }


def flag_unusual_from_frames(
    symbol: str,
    spot: float,
    chains: Sequence[tuple[str, int, pd.DataFrame, pd.DataFrame]],
    *,
    top_n: int = 25,
    **score_kwargs: Any,
) -> Dict[str, Any]:
    """Score all contracts in provided chain frames; return ranked flags."""
    flags: List[Dict[str, Any]] = []
    n_scanned = 0
    for expiry, dte, calls, puts in chains:
        for right, frame in (("C", calls), ("P", puts)):
            if frame is None or frame.empty:
                continue
            df = frame.copy()
            if "strike" not in df.columns:
                continue
            strikes = _num(df["strike"])
            vol = _num(df["volume"]) if "volume" in df.columns else pd.Series(0.0, index=df.index)
            oi = (
                _num(df["openInterest"])
                if "openInterest" in df.columns
                else pd.Series(0.0, index=df.index)
            )
            if "mid" in df.columns:
                mids = _num(df["mid"])
            else:
                bid = _num(df["bid"]) if "bid" in df.columns else pd.Series(0.0, index=df.index)
                ask = _num(df["ask"]) if "ask" in df.columns else pd.Series(0.0, index=df.index)
                last = (
                    _num(df["lastPrice"])
                    if "lastPrice" in df.columns
                    else pd.Series(0.0, index=df.index)
                )
                mids = pd.Series(
                    [_mid(b, a, l) for b, a, l in zip(bid, ask, last)],
                    index=df.index,
                )
            ivs = (
                _num(df["impliedVolatility"], default=float("nan"))
                if "impliedVolatility" in df.columns
                else (
                    _num(df["iv"], default=float("nan"))
                    if "iv" in df.columns
                    else pd.Series(float("nan"), index=df.index)
                )
            )
            for i in df.index:
                n_scanned += 1
                row = score_contract_row(
                    symbol=symbol,
                    expiry=expiry,
                    dte=int(dte),
                    right=right,
                    strike=float(strikes.loc[i]),
                    spot=spot,
                    volume=float(vol.loc[i]),
                    open_interest=float(oi.loc[i]),
                    mid=float(mids.loc[i]),
                    iv=float(ivs.loc[i]) if math.isfinite(float(ivs.loc[i])) else None,
                    **score_kwargs,
                )
                if row:
                    flags.append(row)

    flags.sort(key=lambda r: (-r["score"], -(r.get("premium") or 0)))
    top = flags[: max(1, top_n)] if flags else []
    return {
        "ok": True,
        "symbol": symbol.upper().replace(".US", ""),
        "spot": float(spot),
        "n_scanned": int(n_scanned),
        "n_flagged": len(flags),
        "flags": top,
        "all_flags_count": len(flags),
        "unusual": top,
        "methodology": "chain_aggregate_proxy",
        "methodology_note": (
            "Unusual activity from same-day chain volume/OI/premium aggregates "
            "(yfinance). Not OPRA prints, dark-pool tape, or multi-exchange sweeps."
        ),
        "asof_utc": datetime.now(timezone.utc).isoformat(),
        "session_label": "latest_chain_snapshot",
    }


def scan_symbol(
    symbol: str,
    *,
    max_expiries: int = 6,
    max_dte: int = 45,
    top_n: int = 25,
) -> Dict[str, Any]:
    if yf is None:
        return {
            "ok": False,
            "symbol": symbol,
            "error": "yfinance not installed",
            "flags": [],
            "unusual": [],
            "n_flagged": 0,
            "methodology": "chain_aggregate_proxy",
        }
    sym = symbol.upper().replace(".US", "")
    t = yf.Ticker(sym)
    hist = t.history(period="5d")
    if hist is None or hist.empty:
        return {
            "ok": False,
            "symbol": sym,
            "error": f"no spot for {sym}",
            "flags": [],
            "unusual": [],
            "n_flagged": 0,
            "methodology": "chain_aggregate_proxy",
        }
    spot = float(hist["Close"].iloc[-1])
    expiries = list(t.options or [])
    if not expiries:
        return {
            "ok": False,
            "symbol": sym,
            "spot": spot,
            "error": f"no options chain for {sym}",
            "flags": [],
            "unusual": [],
            "n_flagged": 0,
            "methodology": "chain_aggregate_proxy",
        }

    now = pd.Timestamp.utcnow().tz_localize(None).normalize()
    picked: List[tuple[str, int, pd.DataFrame, pd.DataFrame]] = []
    for exp in expiries:
        try:
            dte = int((pd.Timestamp(exp) - now).days)
        except Exception:
            continue
        if dte < 0 or dte > max_dte:
            continue
        try:
            chain = t.option_chain(exp)
            picked.append((exp, dte, chain.calls.copy(), chain.puts.copy()))
        except Exception:
            continue
        if len(picked) >= max_expiries:
            break

    if not picked:
        return {
            "ok": False,
            "symbol": sym,
            "spot": spot,
            "error": "no expiries in window",
            "flags": [],
            "unusual": [],
            "n_flagged": 0,
            "available_expiries": expiries[:12],
            "methodology": "chain_aggregate_proxy",
        }

    out = flag_unusual_from_frames(sym, spot, picked, top_n=top_n)
    out["available_expiries"] = expiries
    out["expiries_used"] = [e for e, _, _, _ in picked]
    out["ok"] = True
    return out


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description="Unusual options flow flags (chain proxy)")
    p.add_argument("--symbol", required=True)
    p.add_argument("--max-expiries", type=int, default=6)
    p.add_argument("--max-dte", type=int, default=45)
    p.add_argument("--top", type=int, default=25)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    result = scan_symbol(
        args.symbol,
        max_expiries=args.max_expiries,
        max_dte=args.max_dte,
        top_n=args.top,
    )
    payload = _jsonable(result)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(json.dumps(payload))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
