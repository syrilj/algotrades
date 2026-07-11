#!/usr/bin/env python3
"""LSE live GEX / flow snapshot.

London Strategic Edge (`lse-data`) chain rows include gamma/delta/iv/volume_today/
premium_today but **not open interest**. Classic OI-weighted GEX is therefore
unavailable. We use volume_today (fallback: premium_today) as the activity weight:

  CustomerGEX  = Γ * weight * 100 * S² * 0.01
  DealerGEX    = -CustomerGEX   # assume dealers short customer long options
  NetDealerGEX = sum(DealerGEX)

Positive near-spot dealer GEX → pin / mean-revert bias
Negative near-spot dealer GEX → amplify / trend bias

Also pulls options_flow for OTM call premium / call:put premium ratio.

Requires: LSE_API_KEY in env or .env at repo root.
Research only — not a backtest claim.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from lse import LSE

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "models" / "poc_va_gex" / "artifacts"
OUT.mkdir(parents=True, exist_ok=True)


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def client() -> LSE:
    _load_dotenv()
    key = os.environ.get("LSE_API_KEY")
    if not key:
        raise RuntimeError("LSE_API_KEY missing — set in .env or environment")
    return LSE(api_key=key)


def _as_df(obj) -> pd.DataFrame:
    if isinstance(obj, pd.DataFrame):
        return obj
    return pd.DataFrame(obj)


def snapshot(sym: str, max_dte: int = 30, min_flow_premium: float = 25_000) -> dict:
    c = client()
    chain = _as_df(c.options(sym, max_dte=max_dte))
    flow = _as_df(c.options_flow(sym, min_premium=min_flow_premium))

    if chain.empty or "underlying_price" not in chain.columns:
        raise RuntimeError(f"empty/invalid chain for {sym}")

    S = float(chain["underlying_price"].dropna().iloc[0])
    df = chain.dropna(subset=["gamma"]).copy()
    df["volume_today"] = df.get("volume_today", 0).fillna(0).astype(float)
    df["premium_today"] = df.get("premium_today", 0).fillna(0).astype(float)
    df["is_call"] = df["contract_type"].astype(str).str.lower().eq("call")

    w = df["volume_today"].clip(lower=0)
    weight_used = "volume_today"
    if float(w.sum()) <= 0:
        w = df["premium_today"].clip(lower=0)
        weight_used = "premium_today"

    cust = df["gamma"].astype(float) * w * 100.0 * (S**2) * 0.01
    dealer = -cust
    df["dealer_gex_volw"] = dealer
    net = float(dealer.sum())

    calls = df[df.is_call]
    puts = df[~df.is_call]

    def wall(side: pd.DataFrame) -> float | None:
        if side.empty:
            return None
        g = side.groupby("strike")["dealer_gex_volw"].sum().abs()
        return float(g.idxmax()) if len(g) else None

    call_wall = wall(calls)
    put_wall = wall(puts)
    near = df[df["strike"].between(S * 0.9, S * 1.1)]
    near_net = float(near["dealer_gex_volw"].sum()) if len(near) else net

    otm_calls = calls[calls["strike"] > S]
    otm_call_vol = float(otm_calls["volume_today"].sum())
    otm_call_prem = float(otm_calls["premium_today"].sum())
    total_call_vol = float(calls["volume_today"].sum()) or 1.0

    flow_stats: dict = {}
    if not flow.empty and "gamma" in flow.columns:
        fl = flow.dropna(subset=["gamma"]).copy()
        fl["volume"] = fl.get("volume", 0).fillna(0).astype(float)
        fl["premium"] = fl.get("premium", 0).fillna(0).astype(float)
        fl["is_call"] = fl["contract_type"].astype(str).str.lower().eq("call")
        fl_cust = fl["gamma"].astype(float) * fl["volume"] * 100.0 * (S**2) * 0.01
        put_prem = float(fl.loc[~fl.is_call, "premium"].sum())
        call_prem = float(fl.loc[fl.is_call, "premium"].sum())
        flow_stats = {
            "flow_n": int(len(fl)),
            "flow_net_dealer_gex": float((-fl_cust).sum()),
            "flow_call_premium": call_prem,
            "flow_put_premium": put_prem,
            "flow_call_put_premium_ratio": call_prem / max(put_prem, 1.0),
            "flow_otm_call_premium": float(
                fl.loc[fl.is_call & (fl["strike"] > S), "premium"].sum()
            ),
        }

    vol_z = None
    try:
        bars = _as_df(c.candles(sym, timeframe="1d"))
        if "volume" in bars.columns and len(bars) >= 25:
            v = bars["volume"].astype(float)
            mu = float(v.tail(21).iloc[:-1].mean())
            sd = float(v.tail(21).iloc[:-1].std())
            if sd > 0:
                vol_z = float((v.iloc[-1] - mu) / sd)
    except Exception as exc:  # noqa: BLE001 — research path
        flow_stats["candle_error"] = str(exc)

    gex_sign = int(np.sign(near_net)) if near_net else 0
    if near_net > 0:
        regime = "positive_gex_pin"
    elif near_net < 0:
        regime = "negative_gex_amplify"
    else:
        regime = "flat"

    out = {
        "source": "lse-data",
        "symbol": sym,
        "spot": S,
        "max_dte": max_dte,
        "weight": weight_used,
        "note": "OI unavailable on LSE chain; volume/premium weighted proxy",
        "net_dealer_gex_volw": net,
        "near_spot_dealer_gex": near_net,
        "gex_sign": gex_sign,
        "regime": regime,
        "call_wall": call_wall,
        "put_wall": put_wall,
        "dist_call_wall_pct": ((call_wall - S) / S * 100) if call_wall else None,
        "dist_put_wall_pct": ((put_wall - S) / S * 100) if put_wall else None,
        "otm_call_volume": otm_call_vol,
        "otm_call_premium": otm_call_prem,
        "otm_call_volume_share": otm_call_vol / total_call_vol,
        "underlying_volume_z_approx": vol_z,
        **flow_stats,
    }
    df.to_csv(OUT / f"lse_gex_volw_{sym}.csv", index=False)
    if not flow.empty:
        flow.to_csv(OUT / f"lse_flow_{sym}.csv", index=False)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=["TSLA", "QQQ", "SPY", "MU"])
    ap.add_argument("--max-dte", type=int, default=30)
    args = ap.parse_args()

    summary: dict = {}
    for sym in args.symbols:
        print("===", sym)
        try:
            s = snapshot(sym, max_dte=args.max_dte)
            summary[sym] = s
            keys = [
                "spot",
                "regime",
                "gex_sign",
                "near_spot_dealer_gex",
                "call_wall",
                "put_wall",
                "otm_call_volume_share",
                "flow_call_put_premium_ratio",
                "flow_otm_call_premium",
                "underlying_volume_z_approx",
            ]
            print(json.dumps({k: s[k] for k in keys if k in s}, indent=2))
        except Exception as exc:  # noqa: BLE001
            print("FAIL", exc)
            summary[sym] = {"error": str(exc)}

    path = OUT / "lse_gex_flowweighted.json"
    path.write_text(json.dumps(summary, indent=2))
    print("Wrote", path)


if __name__ == "__main__":
    main()
