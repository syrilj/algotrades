#!/usr/bin/env python3
"""Live/research VPA + VWAP scan for any symbols.

Outputs CALL / PUT / FLAT bias with Coulling tags + swing VWAP peg.
Research tool — does NOT claim 80% WR live validity.

Usage:
  .venv/bin/python tools/vpa_scan.py --symbols TSLA,MSTR,NVDA,HOOD
  .venv/bin/python tools/vpa_scan.py --symbols TSLA,NVDA --json
  .venv/bin/python tools/vpa_scan.py --with-sectors --json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
V31 = ROOT / "models" / "poc_va_macdha" / "v31_vpa_vwap"
DNA_PATH = V31 / "vwap_dna.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _norm_sym(s: str) -> str:
    s = s.strip().upper().replace(".US", "")
    return s


def _yf_ohlcv(symbol: str, period: str = "1y") -> pd.DataFrame:
    h = yf.download(symbol, period=period, auto_adjust=True, progress=False)
    if h is None or h.empty:
        return pd.DataFrame()
    if isinstance(h.columns, pd.MultiIndex):
        h.columns = [c[0].lower() for c in h.columns]
    else:
        h.columns = [str(c).lower() for c in h.columns]
    need = ["open", "high", "low", "close", "volume"]
    for c in need:
        if c not in h.columns:
            return pd.DataFrame()
    out = h[need].astype(float).dropna()
    if getattr(out.index, "tz", None) is not None:
        out.index = out.index.tz_localize(None)
    return out


def _dna_policy(symbol: str, dna: dict) -> dict:
    base = dict(dna.get("defaults") or {})
    by = dna.get("by_symbol") or {}
    key = _norm_sym(symbol)
    if key in by:
        base.update(by[key])
    return base


def scan_symbol(symbol: str, vpa_mod, vwap_mod, dna: dict, period: str = "1y") -> dict[str, Any]:
    sym = _norm_sym(symbol)
    df = _yf_ohlcv(sym, period=period)
    if df.empty or len(df) < 40:
        return {"symbol": sym, "ok": False, "error": "insufficient data"}

    vpa = vpa_mod.vpa_frame(df, look=5, vol_sma=20)
    peg = vwap_mod.swing_anchored_vwap(df)
    row_v = vpa.iloc[-1]
    row_p = peg.iloc[-1]
    policy = _dna_policy(sym, dna)

    # Bias
    call = bool(row_v.get("call", False))
    put = bool(row_v.get("put", False))
    if "call_sniper" in vpa.columns and bool(row_v.get("call_sniper", False)):
        call = True
    if "put_sniper" in vpa.columns and bool(row_v.get("put_sniper", False)):
        put = True

    above = bool(row_p.get("above_vwap", False))
    pol = str(policy.get("policy", "soft"))
    peg_ok_call = bool(row_p.get("call_peg_ok", above))
    peg_ok_put = bool(row_p.get("put_peg_ok", not above))

    # Soft / hard / off peg interaction for display
    if call and put:
        bias = "CONFLICT"
        action = "stand_aside"
    elif call:
        if pol == "hard" and not peg_ok_call:
            bias = "CALL_WEAK"
            action = "skip_or_half_size — VPA call but against hard VWAP DNA"
        elif pol == "off":
            bias = "CALL"
            action = "consider_call — VPA (VWAP DNA off for this name)"
        elif not peg_ok_call:
            bias = "CALL_SOFT"
            action = "consider_call_half — VPA call, fighting peg"
        else:
            bias = "CALL"
            action = "consider_call — VPA + peg aligned"
    elif put:
        if pol == "hard" and not peg_ok_put:
            bias = "PUT_WEAK"
            action = "skip_or_half_size — VPA put but against hard VWAP DNA"
        elif pol == "off":
            bias = "PUT"
            action = "consider_put — VPA (VWAP DNA off for this name)"
        elif not peg_ok_put:
            bias = "PUT_SOFT"
            action = "consider_put_half — VPA put, fighting peg"
        else:
            bias = "PUT"
            action = "consider_put — VPA + peg aligned"
    else:
        bias = "FLAT"
        action = "no_flip — wait for VPA event"

    tag = vpa_mod.tag_bar(row_v.to_dict()) if hasattr(vpa_mod, "tag_bar") else ""
    close = float(row_v["close"])
    vwap = float(row_p["vwap"]) if np.isfinite(row_p.get("vwap", np.nan)) else float("nan")
    dist = float(row_p.get("dist_vwap_atr", np.nan)) if np.isfinite(row_p.get("dist_vwap_atr", np.nan)) else None

    return {
        "symbol": sym,
        "ok": True,
        "asof_bar": str(vpa.index[-1].date()),
        "close": close,
        "bias": bias,
        "action": action,
        "side_hint": "call" if "CALL" in bias else ("put" if "PUT" in bias else "flat"),
        "vpa_tag": tag,
        "vwap": vwap,
        "above_vwap": above,
        "dist_vwap_atr": dist,
        "vwap_policy": pol,
        "vol_ratio": float(row_v.get("vol_ratio", 1.0) or 1.0),
        "flags": {
            "stopping_volume": bool(row_v.get("stopping_volume", False)),
            "topping_volume": bool(row_v.get("topping_volume", False)),
            "no_demand": bool(row_v.get("no_demand", False)),
            "no_supply": bool(row_v.get("no_supply", False)),
            "stopping_reclaim": bool(row_v.get("stopping_reclaim", False)),
            "topping_fail": bool(row_v.get("topping_fail", False)),
            "spring": bool(row_v.get("spring", False)),
            "upthrust": bool(row_v.get("upthrust", False)),
            "confirm_up": bool(row_v.get("confirm_up", False)),
            "dump": bool(row_v.get("dump", False)),
            "chase_long": bool(row_p.get("chase_long", False)),
            "chase_short": bool(row_p.get("chase_short", False)),
        },
    }


def run_scan(symbols: list[str], with_sectors: bool = False) -> dict[str, Any]:
    vpa_mod = _load("vpa_scan_vpa", V31 / "vpa.py")
    vwap_mod = _load("vpa_scan_vwap", V31 / "vwap_peg.py")
    dna = json.loads(DNA_PATH.read_text()) if DNA_PATH.exists() else {"defaults": {"policy": "soft"}, "by_symbol": {}}

    rows = []
    for s in symbols:
        try:
            rows.append(scan_symbol(s, vpa_mod, vwap_mod, dna))
        except Exception as e:  # noqa: BLE001
            rows.append({"symbol": _norm_sym(s), "ok": False, "error": str(e)})

    # Sort: CALL first, then PUT, then weak, then flat
    order = {"CALL": 0, "CALL_SOFT": 1, "PUT": 2, "PUT_SOFT": 3, "CALL_WEAK": 4, "PUT_WEAK": 5, "CONFLICT": 6, "FLAT": 7}
    rows.sort(key=lambda r: order.get(r.get("bias", "FLAT"), 9))

    out: dict[str, Any] = {
        "ok": True,
        "asof": datetime.now(timezone.utc).isoformat(),
        "disclaimer": (
            "RESEARCH SCAN ONLY — VPA+VWAP bias tags. "
            "Not validated at 80% win rate for live auto trading. "
            "Use as discretionary checklist (Coulling effort/result + algo VWAP peg)."
        ),
        "gate_80_wr": False,
        "count": len(rows),
        "calls": [r for r in rows if r.get("ok") and str(r.get("bias", "")).startswith("CALL") and "WEAK" not in r.get("bias", "")],
        "puts": [r for r in rows if r.get("ok") and str(r.get("bias", "")).startswith("PUT") and "WEAK" not in r.get("bias", "")],
        "rows": rows,
    }

    if with_sectors:
        sys.path.insert(0, str(ROOT / "tools"))
        from sector_watchlist import build_watchlist  # noqa: WPS433

        out["sectors"] = build_watchlist()

    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="TSLA,MSTR,NVDA,AMD,META,HOOD,IONQ,MU,AVGO,AAPL")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--with-sectors", action="store_true")
    args = ap.parse_args()
    symbols = [s for s in args.symbols.replace(" ", "").split(",") if s]
    out = run_scan(symbols, with_sectors=args.with_sectors)
    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        print(out["disclaimer"])
        print(f"\nScanned {out['count']} names @ {out['asof']}")
        print("\n=== CALL BIAS ===")
        for r in out["calls"]:
            print(f"  {r['symbol']:6} {r['bias']:10} peg={r.get('vwap_policy')}  {r.get('vpa_tag')}  | {r.get('action')}")
        print("\n=== PUT BIAS ===")
        for r in out["puts"]:
            print(f"  {r['symbol']:6} {r['bias']:10} peg={r.get('vwap_policy')}  {r.get('vpa_tag')}  | {r.get('action')}")
        print("\n=== ALL ===")
        for r in out["rows"]:
            if not r.get("ok"):
                print(f"  {r.get('symbol')} ERR {r.get('error')}")
                continue
            print(
                f"  {r['symbol']:6} {r['bias']:10} close={r['close']:.2f} "
                f"vwap={r.get('vwap', float('nan')):.2f} above={r['above_vwap']}  {r.get('vpa_tag')}"
            )
        if out.get("sectors", {}).get("ok"):
            print("\n=== SECTOR LEADERS ===")
            for s in out["sectors"].get("leaders", [])[:4]:
                print(f"  {s['etf']} {s['sector']} score={s['score']*100:+.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
