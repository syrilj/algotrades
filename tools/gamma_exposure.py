#!/usr/bin/env python3
"""Live gamma exposure snapshot for the Trade Desk.

Uses LSE for spot when LSE_API_KEY is available; falls back to yfinance.
Supports two gamma sources:
  - "oi" (default): yfinance options chain, open-interest weighted.
  - "lse": lse-data options chain, volume/premium weighted.

Computes dealer gamma exposure (GEX), call/put walls, flip strike, expected
move, max pain, and a bullish/bearish/neutral squeeze score.

Sign convention (dealer = long calls / short puts, SpotGamma-style):
  GEX = Γ · OI · 100 · S² · 0.01, calls +, puts −
  NetGEX  = sum(calls) + sum(puts)
  +GEX  → pinning / mean-reversion
  -GEX  → amplification / trend continuation
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "services"))

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # noqa: BLE001
    pass


def _yf_symbol(sym: str) -> str:
    return sym.strip().upper().replace(".US", "")


def _lse_symbol(sym: str) -> str:
    s = sym.strip().upper().replace(".US", "")
    # LSE FX convention is CCY/CCY (e.g. EUR/GBP)
    if len(s) == 6 and s.isalpha() and "/" not in s:
        s = f"{s[:3]}/{s[3:]}"
    return s


def _get_spot_yf(symbol: str) -> float:
    t = yf.Ticker(_yf_symbol(symbol))
    hist = t.history(period="5d")
    if hist is None or hist.empty:
        raise RuntimeError(f"no yfinance spot for {symbol}")
    return float(hist["Close"].iloc[-1])


def _get_spot_lse(symbol: str) -> tuple[float | None, str | None]:
    try:
        from services.market_runtime import LSEAdapter
    except Exception as exc:  # noqa: BLE001
        return None, f"LSE import failed: {exc}"

    key = os.environ.get("LSE_API_KEY")
    if not key:
        return None, "LSE_API_KEY not set"

    try:
        adapter = LSEAdapter(api_key=key)
        start = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        candles = adapter.client.candles(_lse_symbol(symbol), "1d", start=start, limit=2)
        if not candles:
            return None, "LSE returned empty candles"
        df = pd.DataFrame(candles)
        if df.empty or "close" not in df.columns:
            return None, "LSE candles missing close"
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            df = df.sort_values("timestamp")
        return float(df["close"].astype(float).iloc[-1]), None
    except Exception as exc:  # noqa: BLE001
        return None, f"LSE spot failed: {exc}"


def _get_spot(symbol: str, spot_source: str) -> tuple[float, str, str | None]:
    if spot_source not in ("auto", "lse"):
        return _get_spot_yf(symbol), "yfinance", None
    lse_spot, lse_err = _get_spot_lse(symbol)
    if lse_spot is not None and np.isfinite(lse_spot) and lse_spot > 0:
        return lse_spot, "lse", lse_err
    return _get_spot_yf(symbol), "yfinance", lse_err


def _bs_gamma(S: float, K: float, T: float, r: float, sigma: float) -> float:
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    sqrtT = np.sqrt(T)
    d1 = (np.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrtT)
    return float(norm.pdf(d1) / (S * sigma * sqrtT))


def _max_pain(call_strikes: np.ndarray, call_oi: np.ndarray, put_strikes: np.ndarray, put_oi: np.ndarray, strikes: list[float]) -> float | None:
    if not strikes:
        return None
    strike_arr = np.array(strikes)
    pains = []
    for K in strike_arr:
        call_value = float(np.sum(np.maximum(0.0, K - call_strikes) * call_oi))
        put_value = float(np.sum(np.maximum(0.0, put_strikes - K) * put_oi))
        pains.append(call_value + put_value)
    return float(strike_arr[np.argmin(pains)])


def _build_lse_client():
    try:
        from lse import LSE
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"LSE import failed: {exc}")
    key = os.environ.get("LSE_API_KEY")
    if not key:
        raise RuntimeError("LSE_API_KEY not set")
    return LSE(api_key=key)


def _as_df(obj) -> pd.DataFrame:
    if isinstance(obj, pd.DataFrame):
        return obj
    return pd.DataFrame(obj)


def _zero_gamma_flip(net_by_strike, spot: float):
    """Strike where cumulative net GEX crosses zero, nearest to spot (linear interp).

    Replaces cum.abs().idxmin(), which picked the near-zero low-strike tail
    (e.g. APLD flip=10 with spot 31.15).
    """
    cum = net_by_strike.sort_index().cumsum()
    strikes = cum.index.to_numpy(dtype=float)
    vals = cum.to_numpy(dtype=float)
    crossings: list[float] = []
    for i in range(len(vals) - 1):
        a, b = vals[i], vals[i + 1]
        if a == 0.0:
            crossings.append(float(strikes[i]))
        elif a * b < 0:
            crossings.append(float(strikes[i] + (strikes[i + 1] - strikes[i]) * (0.0 - a) / (b - a)))
    if len(vals) and vals[-1] == 0.0:
        crossings.append(float(strikes[-1]))
    if not crossings:
        return None
    return float(min(crossings, key=lambda k: abs(k - spot)))


def _compute_squeeze_score(
    spot: float,
    call_wall: float | None,
    put_wall: float | None,
    flip: float | None,
    near_net: float,
    net_dealer: float,
    otm_call_weight: float,
    otm_put_weight: float,
    total_weight: float,
    by_strike: list[dict],
    expected_move_pct: float | None,
    expected_move_low: float | None,
    expected_move_high: float | None,
) -> dict:
    """Compute a bullish/bearish/neutral squeeze score from gamma exposure.

    Returns a dict with squeeze_score (-100..100), squeeze_label, and the
    components that drove the score for transparency.
    """
    total_weight = max(total_weight, 1.0)
    call_wall_gex = 0.0
    put_wall_gex = 0.0
    for s in by_strike:
        if call_wall is not None and abs(s["strike"] - call_wall) < 1e-9:
            call_wall_gex = abs(s.get("call_gex", 0.0))
        if put_wall is not None and abs(s["strike"] - put_wall) < 1e-9:
            put_wall_gex = abs(s.get("put_gex", 0.0))

    # 1. Call wall proximity (0 to +30)
    # Positive when spot is near the call wall: close from below (breakout) or
    # just above from support. Tapers to zero outside ±5%.
    call_wall_dist_pct = ((call_wall - spot) / spot * 100) if call_wall is not None else 999.0
    if -5 <= call_wall_dist_pct <= 5:
        call_prox_score = 30.0 * (1 - abs(call_wall_dist_pct) / 5)
    else:
        call_prox_score = 0.0

    # 2. Put wall proximity (0 to -30)
    # Negative when spot is near the put wall: close from below (support broken)
    # or close from above (break risk). Tapers to zero outside ±5%.
    put_wall_dist_pct = ((put_wall - spot) / spot * 100) if put_wall is not None else 999.0
    if -5 <= put_wall_dist_pct <= 5:
        put_prox_score = -30.0 * (1 - abs(put_wall_dist_pct) / 5)
    else:
        put_prox_score = 0.0

    # 3/4. OTM concentration, using OI if available, else volume.
    call_conc = otm_call_weight / total_weight
    put_conc = otm_put_weight / total_weight
    call_conc_score = min(15.0, call_conc * 100)
    put_conc_score = -min(15.0, put_conc * 100)

    # 5. Wall strength asymmetry (-10 to +10)
    if call_wall_gex > 0 and put_wall_gex > 0:
        wall_ratio = call_wall_gex / put_wall_gex
    elif call_wall_gex > 0:
        wall_ratio = float("inf")
    elif put_wall_gex > 0:
        wall_ratio = 0.0
    else:
        wall_ratio = 1.0  # neither wall carries measurable gamma; treat as balanced
    if wall_ratio > 2:
        wall_asym_score = 10.0
    elif wall_ratio < 0.5:
        wall_asym_score = -10.0
    else:
        wall_asym_score = 0.0

    # 6. Expected move reach (-10 to +10). NOTE: expected_move_low/high are always
    # spot*(1-move_pct)/spot*(1+move_pct), so spot's *position* in that band is always
    # the exact midpoint by construction — scoring that position is a tautology that
    # always nets to zero. Instead score whether the wall driving the live directional
    # read (call wall for a bullish setup, put wall for a bearish one) sits inside the
    # current expiry's 1-SD expected move — i.e. whether it's statistically reachable —
    # tapering to 0 as it sits further outside the band.
    em_score = 0.0
    if expected_move_low is not None and expected_move_high is not None:
        if call_wall is not None and call_prox_score > 0:
            if call_wall <= expected_move_high:
                em_score = 10.0
            else:
                overshoot_pct = (call_wall - expected_move_high) / spot * 100
                em_score = max(0.0, 10.0 - overshoot_pct * 4)
        elif put_wall is not None and put_prox_score < 0:
            if put_wall >= expected_move_low:
                em_score = -10.0
            else:
                overshoot_pct = (expected_move_low - put_wall) / spot * 100
                em_score = min(0.0, -10.0 + overshoot_pct * 4)

    # 7. Flip distance: if spot is close to the flip, regime is unstable.
    flip_score = 0.0
    if flip is not None:
        dist_flip_pct = abs((flip - spot) / spot * 100)
        if dist_flip_pct <= 3:
            flip_score = 5.0 if (spot > flip and call_prox_score > 0) else (-5.0 if (spot < flip and put_prox_score < 0) else 0.0)

    # 8. Regime multiplier: negative near-spot GEX is the fuel. It does not
    # have a directional sign on its own; direction comes from the wall,
    # concentration, and expected-move components above. Positive GEX means
    # pinning and is suppressed to neutral.
    directional_net = call_prox_score + put_prox_score + call_conc_score + put_conc_score + wall_asym_score + em_score + flip_score
    direction = 0.0
    if directional_net > 0:
        direction = 1.0
    elif directional_net < 0:
        direction = -1.0

    if near_net < 0 and direction != 0:
        # Fuel is the share of negative near-spot GEX relative to the total dealer book.
        negative_fuel = min(1.0, abs(near_net) / max(1.0, abs(net_dealer)))
        regime_score = 20.0 * direction * negative_fuel
        call_prox_score *= negative_fuel
        put_prox_score *= negative_fuel
        call_conc_score *= negative_fuel
        put_conc_score *= negative_fuel
        wall_asym_score *= negative_fuel
        em_score *= negative_fuel
        flip_score *= negative_fuel
    else:
        regime_score = 0.0
        # Positive gamma (or no net) means no squeeze: zero the directional components.
        call_prox_score = put_prox_score = call_conc_score = put_conc_score = wall_asym_score = em_score = flip_score = 0.0

    score = regime_score + call_prox_score + put_prox_score + call_conc_score + put_conc_score + wall_asym_score + em_score + flip_score
    score = max(-100.0, min(100.0, score))

    if score >= 20:
        label = "bullish_squeeze"
    elif score <= -20:
        label = "bearish_squeeze"
    else:
        label = "neutral"

    return {
        "squeeze_score": round(score, 1),
        "squeeze_label": label,
        "squeeze_components": {
            "regime_score": regime_score,
            "call_prox_score": call_prox_score,
            "put_prox_score": put_prox_score,
            "call_conc_score": call_conc_score,
            "put_conc_score": put_conc_score,
            "wall_asym_score": wall_asym_score,
            "em_score": em_score,
            "flip_score": flip_score,
        },
        "call_wall_gex": call_wall_gex,
        "put_wall_gex": put_wall_gex,
    }


def compute_gamma_exposure_oi(
    symbol: str,
    spot: float,
    spot_source: str,
    lse_err: str | None,
    max_expiries: int = 4,
    max_dte: int = 120,
    near_spot_pct: float = 0.10,
) -> dict:
    """OI-weighted GEX from yfinance."""
    sym = _yf_symbol(symbol)
    t = yf.Ticker(sym)
    expiries_all = list(t.options or [])
    if not expiries_all:
        raise RuntimeError(f"no options chain for {sym}")

    now = pd.Timestamp.utcnow().tz_localize(None)
    expiries = []
    for exp in expiries_all:
        dte = (pd.Timestamp(exp) - now).days
        if dte <= 0 or dte > max_dte:
            continue
        expiries.append(exp)
        if len(expiries) >= max_expiries:
            break
    if not expiries:
        raise RuntimeError(f"no expiry within 1-{max_dte} DTE for {sym}")

    rows = []
    for exp in expiries:
        ch = t.option_chain(exp)
        dte = max((pd.Timestamp(exp) - now).days, 1)
        T = dte / 365.25
        for side, chain_df, side_sign in (("call", ch.calls, +1.0), ("put", ch.puts, -1.0)):
            if chain_df.empty:
                continue
            df = chain_df.copy()
            df["side"] = side
            df["oi"] = pd.to_numeric(df.get("openInterest", 0), errors="coerce").fillna(0)
            df["volume"] = pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0)
            df["iv"] = pd.to_numeric(df.get("impliedVolatility", np.nan), errors="coerce")
            df["strike"] = pd.to_numeric(df["strike"], errors="coerce")
            df = df[(df["iv"] > 0.005) & df["iv"].notna()]
            df = df[(df["oi"] > 0) | (df["volume"] > 0)]
            for r in df.itertuples(index=False):
                K = float(r.strike)
                iv = float(r.iv)
                oi = float(r.oi)
                vol = float(r.volume)
                g = _bs_gamma(spot, K, T, 0.0, iv)
                dealer = side_sign * g * oi * 100.0 * (spot ** 2) * 0.01
                cust = -dealer
                rows.append(
                    {
                        "expiry": exp,
                        "side": side,
                        "strike": K,
                        "oi": oi,
                        "volume": vol,
                        "iv": iv,
                        "gamma": g,
                        "customer_gex": cust,
                        "dealer_gex": dealer,
                        "moneyness": K / spot,
                        "otm": (side == "call" and K > spot) or (side == "put" and K < spot),
                    }
                )

    if not rows:
        raise RuntimeError(f"empty chain after filters for {sym}")

    df = pd.DataFrame(rows)
    net_dealer = float(df["dealer_gex"].sum())

    call_gex = df[df.side == "call"].groupby("strike")["dealer_gex"].sum()
    put_gex = df[df.side == "put"].groupby("strike")["dealer_gex"].sum()
    net_by_strike = call_gex.add(put_gex, fill_value=0).sort_index()

    call_wall = float(call_gex.abs().idxmax()) if len(call_gex) else None
    put_wall = float(put_gex.abs().idxmax()) if len(put_gex) else None

    near = df[df["strike"].between(spot * (1 - near_spot_pct), spot * (1 + near_spot_pct))]
    near_net = float(near["dealer_gex"].sum()) if len(near) else net_dealer
    gex_sign = int(np.sign(near_net)) if near_net != 0 else 0
    if near_net > 0:
        regime = "positive_gex_pin"
    elif near_net < 0:
        regime = "negative_gex_amplify"
    else:
        regime = "flat"

    flip = _zero_gamma_flip(net_by_strike, spot) if len(net_by_strike) else None

    by_strike = [
        {
            "strike": float(k),
            "net_gex": float(net_by_strike.get(k, 0.0)),
            "call_gex": float(call_gex.get(k, 0.0)),
            "put_gex": float(put_gex.get(k, 0.0)),
        }
        for k in sorted(df["strike"].unique())
    ]

    # Expected move from nearest expiry ATM IV
    nearest_exp = expiries[0]
    dte_nearest = max((pd.Timestamp(nearest_exp) - now).days, 1)
    df_nearest = df[df.expiry == nearest_exp]
    call_df = df_nearest[df_nearest.side == "call"]
    put_df = df_nearest[df_nearest.side == "put"]
    expected_move_pct = expected_move_low = expected_move_high = None
    if not call_df.empty and not put_df.empty:
        atm_call = call_df.loc[call_df["strike"].sub(spot).abs().idxmin()]
        atm_put = put_df.loc[put_df["strike"].sub(spot).abs().idxmin()]
        iv_avg = 0.5 * (float(atm_call["iv"]) + float(atm_put["iv"]))
        move_pct = iv_avg * np.sqrt(dte_nearest / 365.25)
        expected_move_pct = float(move_pct * 100)
        expected_move_low = float(spot * (1 - move_pct))
        expected_move_high = float(spot * (1 + move_pct))

    # Max pain from nearest expiry
    max_pain = None
    if not call_df.empty and not put_df.empty:
        strikes = sorted(df_nearest["strike"].unique())
        max_pain = _max_pain(
            call_df["strike"].values,
            call_df["oi"].values,
            put_df["strike"].values,
            put_df["oi"].values,
            strikes,
        )

    otm_calls = df[(df.side == "call") & (df.otm)]
    otm_puts = df[(df.side == "put") & (df.otm)]
    otm_call_volume = float(otm_calls["volume"].sum())
    otm_call_oi = float(otm_calls["oi"].sum())
    otm_put_volume = float(otm_puts["volume"].sum())
    otm_put_oi = float(otm_puts["oi"].sum())
    total_oi = float(df["oi"].sum())
    total_volume = float(df["volume"].sum())

    squeeze = _compute_squeeze_score(
        spot=spot,
        call_wall=call_wall,
        put_wall=put_wall,
        flip=flip,
        near_net=near_net,
        net_dealer=net_dealer,
        otm_call_weight=otm_call_oi,
        otm_put_weight=otm_put_oi,
        total_weight=total_oi,
        by_strike=by_strike,
        expected_move_pct=expected_move_pct,
        expected_move_low=expected_move_low,
        expected_move_high=expected_move_high,
    )

    return {
        "symbol": sym,
        "spot": spot,
        "spot_source": spot_source,
        "source": "oi",
        "lse_error": lse_err,
        "asof_utc": datetime.now(timezone.utc).isoformat(),
        "expiries_used": expiries,
        "net_dealer_gex": net_dealer,
        "near_spot_dealer_gex": near_net,
        "gex_sign": gex_sign,
        "regime": regime,
        "call_wall": call_wall,
        "put_wall": put_wall,
        "call_wall_gex": squeeze["call_wall_gex"],
        "put_wall_gex": squeeze["put_wall_gex"],
        "dist_call_wall_pct": ((call_wall - spot) / spot * 100) if call_wall is not None else None,
        "dist_put_wall_pct": ((put_wall - spot) / spot * 100) if put_wall is not None else None,
        "approx_flip_strike": flip,
        "dist_flip_pct": ((flip - spot) / spot * 100) if flip is not None else None,
        "expected_move_pct": expected_move_pct,
        "expected_move_low": expected_move_low,
        "expected_move_high": expected_move_high,
        "max_pain": max_pain,
        "otm_call_volume": otm_call_volume,
        "otm_call_oi": otm_call_oi,
        "otm_put_volume": otm_put_volume,
        "otm_put_oi": otm_put_oi,
        "total_oi": total_oi,
        "total_volume": total_volume,
        "n_contracts": int(len(df)),
        "weight": "open_interest",
        "sign_convention": "call +, put -; dealer assumed long calls / short puts",
        "by_strike": by_strike,
        "squeeze_score": squeeze["squeeze_score"],
        "squeeze_label": squeeze["squeeze_label"],
        "squeeze_components": squeeze["squeeze_components"],
    }


def compute_gamma_exposure_lse(
    symbol: str,
    spot: float,
    spot_source: str,
    lse_err: str | None,
    max_dte: int = 30,
    near_spot_pct: float = 0.10,
) -> dict:
    """Volume/premium-weighted GEX from lse-data."""
    sym = _yf_symbol(symbol)
    lse_sym = _lse_symbol(symbol)
    client = _build_lse_client()

    try:
        raw = client.options(lse_sym, max_dte=max_dte)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"LSE options failed for {lse_sym}: {exc}")

    chain = _as_df(raw)
    if chain.empty or "underlying_price" not in chain.columns:
        raise RuntimeError(f"empty/invalid LSE options chain for {lse_sym}")

    spot = float(chain["underlying_price"].dropna().iloc[0])
    df = chain.dropna(subset=["gamma"]).copy()
    if df.empty:
        raise RuntimeError(f"no gamma data in LSE chain for {lse_sym}")

    df["volume_today"] = df.get("volume_today", 0).fillna(0).astype(float)
    df["premium_today"] = df.get("premium_today", 0).fillna(0).astype(float)
    df["contract_type"] = df.get("contract_type", "").astype(str).str.lower()
    df["is_call"] = df["contract_type"].eq("call")
    df["side"] = df["is_call"].map({True: "call", False: "put"})
    df["iv"] = pd.to_numeric(df.get("iv", np.nan), errors="coerce")
    df["strike"] = pd.to_numeric(df["strike"], errors="coerce")

    weight = df["volume_today"].clip(lower=0)
    weight_used = "volume_today"
    if float(weight.sum()) <= 0:
        weight = df["premium_today"].clip(lower=0)
        weight_used = "premium_today"

    df["weight"] = weight
    df["side_sign"] = df["is_call"].map({True: 1.0, False: -1.0})
    df["dealer_gex"] = df["side_sign"] * df["gamma"].astype(float) * weight * 100.0 * (spot ** 2) * 0.01
    df["otm"] = (df["is_call"] & (df["strike"] > spot)) | ((~df["is_call"]) & (df["strike"] < spot))

    net_dealer = float(df["dealer_gex"].sum())

    call_gex = df[df["is_call"]].groupby("strike")["dealer_gex"].sum()
    put_gex = df[~df["is_call"]].groupby("strike")["dealer_gex"].sum()
    net_by_strike = call_gex.add(put_gex, fill_value=0).sort_index()

    call_wall = float(call_gex.abs().idxmax()) if len(call_gex) else None
    put_wall = float(put_gex.abs().idxmax()) if len(put_gex) else None

    near = df[df["strike"].between(spot * (1 - near_spot_pct), spot * (1 + near_spot_pct))]
    near_net = float(near["dealer_gex"].sum()) if len(near) else net_dealer
    gex_sign = int(np.sign(near_net)) if near_net != 0 else 0
    if near_net > 0:
        regime = "positive_gex_pin"
    elif near_net < 0:
        regime = "negative_gex_amplify"
    else:
        regime = "flat"

    flip = _zero_gamma_flip(net_by_strike, spot) if len(net_by_strike) else None

    by_strike = [
        {
            "strike": float(k),
            "net_gex": float(net_by_strike.get(k, 0.0)),
            "call_gex": float(call_gex.get(k, 0.0)),
            "put_gex": float(put_gex.get(k, 0.0)),
        }
        for k in sorted(df["strike"].unique())
    ]

    # Expected move: use LSE IV if available, otherwise fall back to nearest-expiry ATM IV.
    expected_move_pct = expected_move_low = expected_move_high = None
    if "iv" in df.columns and df["iv"].notna().any():
        calls = df[df["is_call"]]
        puts = df[~df["is_call"]]
        if not calls.empty and not puts.empty:
            atm_call = calls.loc[calls["strike"].sub(spot).abs().idxmin()]
            atm_put = puts.loc[puts["strike"].sub(spot).abs().idxmin()]
            call_iv = float(atm_call["iv"]) if pd.notna(atm_call.get("iv")) else np.nan
            put_iv = float(atm_put["iv"]) if pd.notna(atm_put.get("iv")) else np.nan
            if not (np.isnan(call_iv) or np.isnan(put_iv)) and call_iv > 0 and put_iv > 0:
                iv_avg = 0.5 * (call_iv + put_iv)
                # Use shortest DTE available in the chain for expected move.
                min_dte = df["dte"].min() if "dte" in df.columns and df["dte"].notna().any() else max_dte
                min_dte = max(int(min_dte), 1)
                move_pct = iv_avg * np.sqrt(min_dte / 365.25)
                expected_move_pct = float(move_pct * 100)
                expected_move_low = float(spot * (1 - move_pct))
                expected_move_high = float(spot * (1 + move_pct))

    max_pain = None

    otm_calls = df[df["is_call"] & df["otm"]]
    otm_puts = df[(~df["is_call"]) & df["otm"]]
    otm_call_volume = float(otm_calls["volume_today"].sum())
    otm_put_volume = float(otm_puts["volume_today"].sum())
    otm_call_oi = 0.0
    otm_put_oi = 0.0
    total_weight = float(weight.sum())
    # Concentration numerators must use the SAME series as total_weight (volume_today
    # or, when it's all zero, premium_today) — otherwise the ratio mixes units when
    # the weight series has fallen back to premium.
    otm_call_weight = float(otm_calls["weight"].sum())
    otm_put_weight = float(otm_puts["weight"].sum())

    squeeze = _compute_squeeze_score(
        spot=spot,
        call_wall=call_wall,
        put_wall=put_wall,
        flip=flip,
        near_net=near_net,
        net_dealer=net_dealer,
        otm_call_weight=otm_call_weight,
        otm_put_weight=otm_put_weight,
        total_weight=total_weight,
        by_strike=by_strike,
        expected_move_pct=expected_move_pct,
        expected_move_low=expected_move_low,
        expected_move_high=expected_move_high,
    )

    return {
        "symbol": sym,
        "spot": spot,
        "spot_source": spot_source,
        "source": "lse",
        "lse_error": lse_err,
        "asof_utc": datetime.now(timezone.utc).isoformat(),
        "expiries_used": [lse_sym],
        "net_dealer_gex": net_dealer,
        "near_spot_dealer_gex": near_net,
        "gex_sign": gex_sign,
        "regime": regime,
        "call_wall": call_wall,
        "put_wall": put_wall,
        "call_wall_gex": squeeze["call_wall_gex"],
        "put_wall_gex": squeeze["put_wall_gex"],
        "dist_call_wall_pct": ((call_wall - spot) / spot * 100) if call_wall is not None else None,
        "dist_put_wall_pct": ((put_wall - spot) / spot * 100) if put_wall is not None else None,
        "approx_flip_strike": flip,
        "dist_flip_pct": ((flip - spot) / spot * 100) if flip is not None else None,
        "expected_move_pct": expected_move_pct,
        "expected_move_low": expected_move_low,
        "expected_move_high": expected_move_high,
        "max_pain": max_pain,
        "otm_call_volume": otm_call_volume,
        "otm_call_oi": otm_call_oi,
        "otm_put_volume": otm_put_volume,
        "otm_put_oi": otm_put_oi,
        "total_oi": 0.0,
        "total_volume": total_weight,
        "n_contracts": int(len(df)),
        "weight": weight_used,
        "sign_convention": "call +, put -; dealer assumed long calls / short puts (volume/premium weighted)",
        "by_strike": by_strike,
        "squeeze_score": squeeze["squeeze_score"],
        "squeeze_label": squeeze["squeeze_label"],
        "squeeze_components": squeeze["squeeze_components"],
    }


def compute_gamma_exposure(
    symbol: str,
    spot_source: str = "auto",
    source: str = "oi",
    max_expiries: int = 4,
    max_dte: int = 120,
    near_spot_pct: float = 0.10,
) -> dict:
    sym = _yf_symbol(symbol)
    spot, spot_src, lse_err = _get_spot(sym, spot_source)
    if not np.isfinite(spot) or spot <= 0:
        raise RuntimeError(f"invalid spot for {sym}")

    if source == "lse":
        return compute_gamma_exposure_lse(
            symbol,
            spot,
            spot_src,
            lse_err,
            max_dte=max_dte,
            near_spot_pct=near_spot_pct,
        )

    return compute_gamma_exposure_oi(
        symbol,
        spot,
        spot_src,
        lse_err,
        max_expiries=max_expiries,
        max_dte=max_dte,
        near_spot_pct=near_spot_pct,
    )


def main():
    ap = argparse.ArgumentParser(description="Gamma exposure snapshot for Trade Desk")
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--spot-source", choices=["auto", "lse", "yfinance"], default="auto")
    ap.add_argument("--source", choices=["oi", "lse"], default="oi",
                    help="Gamma source: oi = yfinance open-interest, lse = lse-data volume/premium")
    ap.add_argument("--max-expiries", type=int, default=4)
    ap.add_argument("--max-dte", type=int, default=120)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        out = compute_gamma_exposure(
            args.symbol,
            spot_source=args.spot_source,
            source=args.source,
            max_expiries=args.max_expiries,
            max_dte=args.max_dte,
        )
    except Exception as e:  # noqa: BLE001
        out = {"ok": False, "error": str(e), "symbol": _yf_symbol(args.symbol)}

    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
