#!/usr/bin/env python3
"""Live GEX snapshot from yfinance option chain.

Sign convention (documented):
  Customer long calls/puts → dealer short both.
  DealerGEX_call = -Gamma * OI * 100 * S^2 * 0.01
  DealerGEX_put  = -Gamma * OI * 100 * S^2 * 0.01
  Net dealer GEX = sum(calls) + sum(puts)  [both negative of customer]

  Positive net dealer GEX => dealers long gamma => pinning
  Negative net dealer GEX => dealers short gamma => amplification

This is a RESEARCH snapshot (EOD OI lag). Not a backtest claim.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "models" / "poc_va_gex" / "artifacts"
OUT.mkdir(parents=True, exist_ok=True)


def bs_gamma(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    sqrtT = np.sqrt(T)
    d1 = (np.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrtT)
    return float(norm.pdf(d1) / (S * sigma * sqrtT))


def gex_row(S, K, T, sigma, oi, customer_sign):
    """customer_sign: +1 for call, +1 for put as customer-long; dealer flips."""
    g = bs_gamma(S, K, T, 0.0, max(float(sigma), 1e-4))
    # dollar GEX per 1% move
    cust = customer_sign * g * float(oi) * 100.0 * (S ** 2) * 0.01
    dealer = -cust
    return g, cust, dealer


def snapshot(ticker: str, max_expiries: int = 4) -> dict:
    t = yf.Ticker(ticker)
    hist = t.history(period="5d")
    if hist.empty:
        raise RuntimeError(f"no spot for {ticker}")
    S = float(hist["Close"].iloc[-1])
    expiries = list(t.options[:max_expiries])
    rows = []
    now = pd.Timestamp.utcnow().tz_localize(None)
    for exp in expiries:
        ch = t.option_chain(exp)
        exp_dt = pd.Timestamp(exp)
        T = max((exp_dt - now).total_seconds() / (365.25 * 24 * 3600), 1 / 365)
        for side, df, sign in (("call", ch.calls, +1), ("put", ch.puts, +1)):
            for _, r in df.iterrows():
                oi = r.get("openInterest", 0) or 0
                vol = r.get("volume", 0) or 0
                iv = r.get("impliedVolatility", np.nan)
                if oi <= 0 and (vol is None or vol == 0 or (isinstance(vol, float) and np.isnan(vol))):
                    continue
                if not np.isfinite(iv) or iv <= 0:
                    continue
                K = float(r["strike"])
                g, cust, dealer = gex_row(S, K, T, iv, oi, sign)
                rows.append(
                    {
                        "expiry": exp,
                        "side": side,
                        "strike": K,
                        "oi": float(oi),
                        "volume": float(vol) if vol == vol else 0.0,
                        "iv": float(iv),
                        "gamma": g,
                        "customer_gex": cust,
                        "dealer_gex": dealer,
                        "moneyness": K / S,
                        "otm": (side == "call" and K > S) or (side == "put" and K < S),
                    }
                )
    df = pd.DataFrame(rows)
    if df.empty:
        return {"ticker": ticker, "spot": S, "error": "empty chain after filters"}

    net_dealer = float(df["dealer_gex"].sum())
    by_strike = df.groupby("strike")["dealer_gex"].sum().sort_index()
    call_wall = float(df[df.side == "call"].groupby("strike")["dealer_gex"].sum().abs().idxmax()) if (df.side == "call").any() else None
    # wall = strike with largest |dealer gex| contribution from that side's customer OI
    call_abs = df[df.side == "call"].groupby("strike")["customer_gex"].sum()
    put_abs = df[df.side == "put"].groupby("strike")["customer_gex"].sum()
    call_wall = float(call_abs.abs().idxmax()) if len(call_abs) else None
    put_wall = float(put_abs.abs().idxmax()) if len(put_abs) else None

    otm_calls = df[(df.side == "call") & (df.otm)]
    otm_call_vol = float(otm_calls["volume"].sum())
    otm_call_oi = float(otm_calls["oi"].sum())

    # crude flip: strike where cumulative dealer gex crosses 0 (from low strikes up)
    cum = by_strike.cumsum()
    flip = None
    if len(cum):
        # nearest strike to zero crossing of cumulative
        flip = float(cum.abs().idxmin())

    out = {
        "ticker": ticker,
        "spot": S,
        "asof_utc": str(now),
        "expiries_used": expiries,
        "net_dealer_gex": net_dealer,
        "gex_sign": int(np.sign(net_dealer)) if net_dealer != 0 else 0,
        "regime": "positive_gex_pin" if net_dealer > 0 else ("negative_gex_amplify" if net_dealer < 0 else "flat"),
        "call_wall": call_wall,
        "put_wall": put_wall,
        "dist_call_wall_pct": ((call_wall - S) / S * 100) if call_wall else None,
        "dist_put_wall_pct": ((put_wall - S) / S * 100) if put_wall else None,
        "approx_flip_strike": flip,
        "otm_call_volume": otm_call_vol,
        "otm_call_oi": otm_call_oi,
        "n_contracts": int(len(df)),
        "sign_convention": "dealer = -customer; customer assumed long calls and puts",
    }
    df.to_csv(OUT / f"gex_chain_{ticker}.csv", index=False)
    (OUT / f"gex_snapshot_{ticker}.json").write_text(json.dumps(out, indent=2))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", default="TSLA,QQQ,SPY,MU")
    ap.add_argument("--max-expiries", type=int, default=4)
    args = ap.parse_args()
    summary = {}
    for raw in args.tickers.split(","):
        ticker = raw.strip().upper()
        print(f"\n=== {ticker} ===")
        try:
            s = snapshot(ticker, args.max_expiries)
            summary[ticker] = s
            print(json.dumps({k: s[k] for k in s if k != "expiries_used"}, indent=2))
        except Exception as e:
            print("FAIL", e)
            summary[ticker] = {"error": str(e)}
    (OUT / "gex_snapshots.json").write_text(json.dumps(summary, indent=2))
    print("\nWrote", OUT / "gex_snapshots.json")


if __name__ == "__main__":
    main()
