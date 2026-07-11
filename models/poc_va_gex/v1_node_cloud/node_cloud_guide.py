#!/usr/bin/env python3
"""Live guide: MA cloud compass + GEX nodes (walls / flip).

Prints which node spot is heading toward. Research / desk helper — not a
backtest claim. Historical SIDE engine: poc_va_macdha/v19_node_cloud.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "models" / "poc_va_gex" / "research"))
from gex_snapshot import snapshot  # noqa: E402

OUT = ROOT / "models" / "poc_va_gex" / "artifacts"
OUT.mkdir(parents=True, exist_ok=True)


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def ma_cloud_state(close: pd.Series, fast: int = 8, mid: int = 21, slow: int = 55) -> dict:
    f, m, s = _ema(close, fast), _ema(close, mid), _ema(close, slow)
    spot = float(close.iloc[-1])
    ef, em, es = float(f.iloc[-1]), float(m.iloc[-1]), float(s.iloc[-1])
    bull = ef > em > es and spot >= em
    bear = ef < em < es and spot <= em
    if bull:
        direction = "up"
    elif bear:
        direction = "down"
    else:
        direction = "neutral"
    return {
        "spot": spot,
        "ema_fast": ef,
        "ema_mid": em,
        "ema_slow": es,
        "direction": direction,
        "cloud_bull": bull,
        "cloud_bear": bear,
    }


def pick_target(spot: float, direction: str, nodes: dict[str, float | None]) -> dict:
    clean = {k: float(v) for k, v in nodes.items() if v is not None and np.isfinite(v)}
    if direction == "up":
        above = {k: v for k, v in clean.items() if v > spot}
        if not above:
            return {"target_node": None, "target_price": None, "room_pct": None, "reason": "no node above"}
        name = min(above, key=above.get)
        px = above[name]
        return {
            "target_node": name,
            "target_price": px,
            "room_pct": (px - spot) / spot * 100.0,
            "reason": "nearest node above (cloud up)",
        }
    if direction == "down":
        below = {k: v for k, v in clean.items() if v < spot}
        if not below:
            return {"target_node": None, "target_price": None, "room_pct": None, "reason": "no node below"}
        name = max(below, key=below.get)
        px = below[name]
        return {
            "target_node": name,
            "target_price": px,
            "room_pct": (spot - px) / spot * 100.0,
            "reason": "nearest node below (cloud down)",
        }
    return {
        "target_node": None,
        "target_price": None,
        "room_pct": None,
        "reason": "cloud neutral — wait, do not force a trade",
    }


def guide(ticker: str, fast: int = 8, mid: int = 21, slow: int = 55) -> dict:
    hist = yf.download(ticker, period="6mo", interval="1d", auto_adjust=True, progress=False)
    if isinstance(hist.columns, pd.MultiIndex):
        hist.columns = [c[0].lower() for c in hist.columns]
    else:
        hist.columns = [str(c).lower() for c in hist.columns]
    if hist.empty or "close" not in hist.columns:
        raise RuntimeError(f"no history for {ticker}")

    cloud = ma_cloud_state(hist["close"], fast, mid, slow)
    gex = snapshot(ticker)
    nodes = {
        "put_wall": gex.get("put_wall"),
        "approx_flip": gex.get("approx_flip_strike"),
        "call_wall": gex.get("call_wall"),
    }
    target = pick_target(cloud["spot"], cloud["direction"], nodes)

    bias = "flat"
    if cloud["cloud_bull"] and target.get("target_node"):
        bias = "reactive_long_toward_node"
    elif cloud["cloud_bear"] and target.get("target_node"):
        bias = "reactive_short_or_stand_aside"  # book is long-biased; prefer stand aside

    out = {
        "ticker": ticker.upper(),
        "idea": "react_not_predict",
        "cloud": cloud,
        "gex_regime": gex.get("regime"),
        "net_dealer_gex": gex.get("net_dealer_gex"),
        "nodes": nodes,
        "target": target,
        "guide_bias": bias,
        "note": "Desk guide only. Historical SIDE = poc_va_macdha/v19_node_cloud.",
    }
    path = OUT / f"node_cloud_guide_{ticker.upper()}.json"
    path.write_text(json.dumps(out, indent=2, default=float))
    out["_wrote"] = str(path)
    return out


def main():
    ap = argparse.ArgumentParser(description="MA cloud + GEX node reactive guide")
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--ema-fast", type=int, default=8)
    ap.add_argument("--ema-mid", type=int, default=21)
    ap.add_argument("--ema-slow", type=int, default=55)
    args = ap.parse_args()
    out = guide(args.ticker, args.ema_fast, args.ema_mid, args.ema_slow)
    print(json.dumps({k: v for k, v in out.items() if not str(k).startswith("_")}, indent=2, default=float))
    print("Wrote", out["_wrote"])


if __name__ == "__main__":
    main()
