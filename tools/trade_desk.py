#!/usr/bin/env python3
"""Trade Desk — live setup tool for poc_va_macdha models.

Usage:
  python3 tools/trade_desk.py TSLA
  python3 tools/trade_desk.py AAPL --model v12_regime_router
  python3 tools/trade_desk.py MU --model auto
  python3 tools/trade_desk.py rank
  python3 tools/trade_desk.py rank --symbol TSLA
  python3 tools/trade_desk.py rotate
  python3 tools/trade_desk.py rotate --top 3
  python3 tools/trade_desk.py picks --horizon day --model v14_risk_kelly
  python3 tools/trade_desk.py risk APLD --account 1000 --conf 0.85 --vol-z 1.8
  python3 tools/trade_desk.py watch NVDA --every 30
  python3 tools/trade_desk.py watch NVDA,MU,ANET --every 45
  python3 tools/trade_desk.py watch rotate --every 90
  python3 tools/trade_desk.py openscan
  python3 tools/trade_desk.py openscan --top 12 --account 10000
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from model_registry import (  # noqa: E402
    DEFAULT_MODEL,
    engine_kind,
    engine_path,
    equity_default_model,
    hist_win_rate,
    list_engine_models,
    rank_models,
    rank_models_for_symbol,
    recommend_model,
)
from risk_manager import (  # noqa: E402
    PortfolioState,
    SetupSnapshot,
    decision_to_dict,
    plan_entry,
)

def _sanitize_nan(obj: Any) -> Any:
    """Replace NaN/±Infinity with None so downstream JSON.parse is safe."""
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_nan(v) for v in obj]
    return obj


def _safe_json(obj: Any, **kwargs: Any) -> str:
    return json.dumps(_sanitize_nan(obj), default=str, **kwargs)


_ENGINE_CACHE: dict[str, Any] = {}

DEFAULT_WATCH = [
    # Mag7 + mega tech
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "NFLX", "AVGO",
    # Memory / semis
    "MU", "SNDK", "WDC", "STX", "AMD", "TSM", "ARM", "SMH", "INTC", "QCOM", "MRVL", "ASML", "KLAC", "AMAT", "LRCX",
    # Photonics / networking / optical
    "COHR", "LITE", "AAOI", "CIEN", "ANET", "CRDO", "FN", "VRT", "GLW", "CSCO",
    # Energy / power / uranium / grid
    "XOM", "CVX", "COP", "SLB", "VST", "CEG", "FSLR", "ENPH", "XLE", "CCJ", "UEC", "OKLO", "NEE", "BE", "ETN",
    # Space / defense
    "RKLB", "ASTS", "PL", "LUNR", "BA", "LMT", "NOC", "RTX", "GE", "TDG", "AXON",
    # Quantum
    "IONQ", "RGTI", "QBTS", "QUBT",
    # AI infra / software / cyber
    "SMCI", "DELL", "HPE", "ORCL", "PLTR", "SNOW", "CRM", "NOW", "DDOG", "NET", "CRWD", "PANW", "ZS", "MDB",
    # Banks / fintech
    "JPM", "BAC", "GS", "MS", "SQ", "HOOD", "PYPL", "V", "MA",
    # Biotech / healthcare
    "LLY", "NVO", "UNH", "ISRG", "VKTX", "MRNA", "REGN",
    # Metals / materials
    "FCX", "NEM", "AA", "GLD", "SLV", "X",
    # Consumer / retail
    "COST", "WMT", "HD", "TJX", "NKE", "SBUX",
    # Crypto / speculative beta
    "COIN", "MSTR", "IBIT", "MARA",
    # Index / sector ETFs
    "SPY", "QQQ", "IWM", "ARKK", "XLF", "XBI", "URA", "XLE", "SMH", "XLK",
]

SECTORS = {
    "mag7": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "NFLX", "AVGO"],
    "memory": ["MU", "SNDK", "WDC", "STX", "AMD", "TSM", "ARM", "SMH", "INTC", "QCOM", "MRVL", "ASML", "KLAC", "AMAT", "LRCX"],
    "photonics": ["COHR", "LITE", "AAOI", "CIEN", "ANET", "CRDO", "FN", "VRT", "GLW", "CSCO"],
    "energy": ["XOM", "CVX", "COP", "SLB", "VST", "CEG", "FSLR", "ENPH", "XLE", "CCJ", "UEC", "OKLO", "NEE", "BE", "ETN"],
    "space": ["RKLB", "ASTS", "PL", "LUNR", "BA", "LMT", "NOC", "RTX", "GE", "TDG", "AXON"],
    "quantum": ["IONQ", "RGTI", "QBTS", "QUBT"],
    "ai_infra": ["SMCI", "DELL", "HPE", "ORCL", "PLTR", "SNOW", "CRM", "NOW", "DDOG", "NET", "CRWD", "PANW", "ZS", "MDB"],
    "banks": ["JPM", "BAC", "GS", "MS", "SQ", "HOOD", "PYPL", "V", "MA", "XLF"],
    "biotech": ["LLY", "NVO", "UNH", "ISRG", "VKTX", "MRNA", "REGN", "XBI"],
    "metals": ["FCX", "NEM", "AA", "GLD", "SLV", "X"],
    "consumer": ["COST", "WMT", "HD", "TJX", "NKE", "SBUX"],
    "crypto": ["COIN", "MSTR", "IBIT", "MARA"],
    "beta": ["SPY", "QQQ", "IWM", "ARKK", "XLK"],
}

SECTOR_ETF = {
    "mag7": "QQQ",
    "memory": "SMH",
    "photonics": None,
    "energy": "XLE",
    "space": None,
    "quantum": None,
    "ai_infra": "XLK",
    "banks": "XLF",
    "biotech": "XBI",
    "metals": "GLD",
    "consumer": None,
    "crypto": "IBIT",
    "beta": "SPY",
}

ROTATION_SECTORS = [
    "mag7", "memory", "photonics", "energy", "space", "quantum",
    "ai_infra", "banks", "biotech", "metals", "consumer", "crypto",
]


def _symbol_sector(sym: str) -> str:
    s = _to_yf(sym)
    for name, members in SECTORS.items():
        if s in members:
            return name
    return "other"


def _download_close(tickers: list[str], period: str = "6mo") -> pd.DataFrame:
    """Adjusted close panel for tickers."""
    data = yf.download(
        tickers,
        period=period,
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    if data is None or data.empty:
        return pd.DataFrame()
    if len(tickers) == 1:
        t = tickers[0]
        if "Close" in data.columns:
            return pd.DataFrame({t: data["Close"]})
        # single multiindex?
        return pd.DataFrame({t: data.iloc[:, 0]})
    closes = {}
    for t in tickers:
        try:
            if isinstance(data.columns, pd.MultiIndex):
                if t in data.columns.get_level_values(0):
                    s = data[t]["Close"] if "Close" in data[t].columns else data[t].iloc[:, 0]
                else:
                    continue
            else:
                s = data["Close"] if "Close" in data.columns else data.iloc[:, 0]
            closes[t] = s
        except Exception:  # noqa: BLE001
            continue
    out = pd.DataFrame(closes).dropna(how="all")
    return out


def _basket_series(members: list[str], period: str = "6mo") -> pd.Series:
    """Equal-weight basket total-return index from members."""
    closes = _download_close(members, period=period)
    if closes.empty:
        return pd.Series(dtype=float)
    rets = closes.pct_change().fillna(0.0)
    basket = (1.0 + rets.mean(axis=1)).cumprod()
    basket.name = "basket"
    return basket


def rank_sector_flows(period: str = "6mo") -> list[dict[str, Any]]:
    """Rank thematic sectors by where money is rotating (RS vs SPY + trend)."""
    # One batched Yahoo pull for SPY + sector ETFs (avoid N serial downloads).
    etf_by_sec = {sec: SECTOR_ETF.get(sec) for sec in ROTATION_SECTORS}
    batch = ["SPY"] + sorted({e for e in etf_by_sec.values() if e})
    panel = _download_close(batch, period=period)
    if panel.empty or "SPY" not in panel.columns:
        raise RuntimeError("Could not download SPY for sector rotation")
    spy_px = panel["SPY"].dropna()

    rows = []
    for sec in ROTATION_SECTORS:
        etf = etf_by_sec.get(sec)
        members = [m for m in SECTORS[sec] if m not in ("SPY", "QQQ", "IWM", "ARKK")]
        try:
            if etf and etf in panel.columns:
                px = panel[etf].dropna()
                proxy = etf
            else:
                px = _basket_series(members[:8], period=period)  # cap for speed
                proxy = f"basket({len(members[:8])})"
            if px.empty or len(px) < 25:
                continue
            # align
            joined = pd.concat([px.rename("sec"), spy_px.rename("spy")], axis=1).dropna()
            if len(joined) < 25:
                continue
            sec_px = joined["sec"]
            spy_a = joined["spy"]
            ret_5 = float(sec_px.iloc[-1] / sec_px.iloc[-6] - 1) if len(sec_px) > 6 else 0.0
            ret_20 = float(sec_px.iloc[-1] / sec_px.iloc[-21] - 1) if len(sec_px) > 21 else 0.0
            spy_5 = float(spy_a.iloc[-1] / spy_a.iloc[-6] - 1) if len(spy_a) > 6 else 0.0
            spy_20 = float(spy_a.iloc[-1] / spy_a.iloc[-21] - 1) if len(spy_a) > 21 else 0.0
            rs_5 = ret_5 - spy_5
            rs_20 = ret_20 - spy_20
            ma20 = float(sec_px.tail(20).mean())
            above_ma = float(sec_px.iloc[-1] > ma20)
            # recent acceleration
            ret_1 = float(sec_px.iloc[-1] / sec_px.iloc[-2] - 1) if len(sec_px) > 2 else 0.0
            # flow score: weight near-term RS hardest (money rotating NOW)
            flow = 0.45 * rs_5 + 0.35 * rs_20 + 0.10 * ret_1 + 0.10 * (0.02 if above_ma else -0.02)
            rows.append(
                {
                    "sector": sec,
                    "proxy": proxy,
                    "ret_5d": round(ret_5, 4),
                    "ret_20d": round(ret_20, 4),
                    "rs_vs_spy_5d": round(rs_5, 4),
                    "rs_vs_spy_20d": round(rs_20, 4),
                    "above_ma20": bool(above_ma),
                    "flow_score": round(flow, 4),
                    "members": members,
                }
            )
        except Exception as exc:  # noqa: BLE001
            rows.append({"sector": sec, "error": str(exc), "flow_score": -9.0, "members": members})

    rows.sort(key=lambda r: r.get("flow_score", -9), reverse=True)
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def rotate_picks(
    account: float,
    risk_pct: float,
    horizon: str,
    model: str,
    top_n: int = 3,
) -> dict[str, Any]:
    """1) Rank sector money flow  2) Scan stocks in top N  3) Return picks."""
    all_flows_sorted = rank_sector_flows()
    top = [r for r in all_flows_sorted if "error" not in r][:top_n]
    symbols: list[str] = []
    for sec in top:
        symbols.extend(sec.get("members") or [])
    seen = set()
    symbols = [s for s in symbols if not (s in seen or seen.add(s))]
    print(f"Top sectors: {', '.join(t['sector'] for t in top)}", flush=True)
    print(f"Scanning {len(symbols)} leaders in those sectors…", flush=True)
    stock_rows = scan_picks(symbols, account, risk_pct, horizon, model=model)
    sec_rank = {r["sector"]: r["rank"] for r in top}
    for row in stock_rows:
        row["sector_flow_rank"] = sec_rank.get(row.get("sector"), 99)
    return {
        "sector_flows": all_flows_sorted,
        "top_sectors": top,
        "stock_picks": stock_rows,
        "scanned": symbols,
    }


def _print_rotate(payload: dict, horizon: str) -> None:
    flows = payload.get("sector_flows") or []
    top = payload.get("top_sectors") or []
    stocks = payload.get("stock_picks") or []

    print()
    print("=" * 72)
    print("  STEP 1 — WHERE IS MONEY FLOWING?  (sector rotation vs SPY)")
    print("=" * 72)
    print(f"  {'#':<3} {'sector':<12} {'5d':>7} {'20d':>7} {'RS5d':>7} {'RS20d':>7} {'flow':>7}  proxy")
    for r in flows:
        if "error" in r:
            print(f"  {r.get('rank','?'):<3} {r['sector']:<12}  ERROR {r['error'][:40]}")
            continue
        mark = " <<<" if r in top or r.get("sector") in {t["sector"] for t in top} else ""
        print(
            f"  {r['rank']:<3} {r['sector']:<12} "
            f"{r['ret_5d']:>6.1%} {r['ret_20d']:>6.1%} "
            f"{r['rs_vs_spy_5d']:>6.1%} {r['rs_vs_spy_20d']:>6.1%} "
            f"{r['flow_score']:>7.3f}  {r.get('proxy','')}{mark}"
        )

    top_names = [t["sector"] for t in top]
    print()
    print("=" * 72)
    print(f"  STEP 2 — TOP {len(top_names)} SECTORS → scan leaders: {', '.join(top_names)}")
    print("=" * 72)

    buy = [r for r in stocks if r.get("setup_kind") in ("classic_buy", "breakout_buy") or r.get("setup_ok")]
    breakouts = [r for r in stocks if r.get("setup_kind") == "breakout_watch" or r.get("action") == "BREAKOUT WATCH"]
    pullbacks = [r for r in stocks if r.get("setup_kind") == "pullback_watch" or r.get("action") == "PULLBACK ZONE"]
    almost = [
        r for r in stocks
        if r.get("action") in ("WAIT", "WAIT (almost ready)")
        and "error" not in r
        and r.get("confidence", 0) >= 0.65
    ]

    print("\n  BUY NOW / BUY BREAKOUT (from hot sectors)")
    if not buy:
        print("    None live — check BREAKOUT WATCH + PULLBACK ZONE below.")
    for r in buy[:12]:
        tag = "BREAKOUT" if r.get("setup_kind") == "breakout_buy" else "CLASSIC"
        eng = r.get("best_hist_model") or r.get("model") or ""
        print(
            f"    [{tag}] {r['symbol']:<5} [{r.get('sector'):<9}]  "
            f"~${r['price']:.2f}  stop ${r['stop']:.2f}  "
            f"risk ${r['dollar_risk']:.0f}  conf {r['confidence']:.0%}  "
            f"best-model {eng}"
        )

    print("\n  ABOUT TO BREAK OUT (volume waking — wait for SURGE through level)")
    if not breakouts:
        print("    None pressing highs in top sectors right now.")
    for r in breakouts[:12]:
        lvl = r.get("breakout_level")
        rv = r.get("rvol")
        tip = f"buy-stop > ${lvl:.2f}" if lvl else (r.get("do_next") or "")[:70]
        rv_s = f" rvol {rv:.1f}x" if rv is not None else ""
        print(
            f"    {r['symbol']:<5} [{r.get('sector'):<9}]  "
            f"${r['price']:.2f}{rv_s}  conf {r['confidence']:.0%}  → {tip}"
        )

    print("\n  PULLBACK ZONE (trend ok — wait for dip into value)")
    if not pullbacks:
        print("    (none)")
    for r in pullbacks[:10]:
        tip = (r.get("do_next") or "")[:80]
        print(f"    {r['symbol']:<5} [{r.get('sector'):<9}]  ${r['price']:.2f}  → {tip}")

    print("\n  OTHER HIGH-CONF WAIT (by sector)")
    for sec in top_names:
        bucket = [r for r in almost if r.get("sector") == sec]
        buy_sec = [r for r in buy if r.get("sector") == sec]
        bo_sec = [r for r in breakouts if r.get("sector") == sec]
        print(f"    — {sec} —")
        shown = buy_sec[:2] + bo_sec[:2] + bucket[:2]
        if not shown:
            print("      (no high-conf names right now)")
            continue
        for r in shown[:5]:
            status = r.get("action") or ("BUY" if r.get("setup_ok") else "WAIT")
            tip = (r.get("do_next") or "")[:75]
            print(f"      [{status}] {r['symbol']:<5} ${r['price']:.2f}  conf {r['confidence']:.0%}  → {tip}")

    print("\n  What this means")
    print("    1) Money is rotating hardest into the sectors marked <<< above")
    print("    2) BUY / BUY BREAKOUT = trade now (breakout needs VOLUME surge)")
    print("    3) BREAKOUT WATCH = almost — only take it when volume expands")
    print("    4) PULLBACK ZONE = prefer dips into 22 EMA / value")
    print("    5) Lost 200 EMA = structural break → skip longs (advisory; not a promoted hard gate)")
    print("    6) Different stocks → different engines:  --model auto")
    print("    7) Drill in:  .venv/bin/python3 tools/trade_desk.py TICKER --model auto")
    print("=" * 72)
    print()

# Historical bag priors — ONLY used when no model+symbol hist_wr exists.
# Do NOT use as a fake live confidence floor for specialists.
_PRIOR_WR = {
    "TSLA": 0.56, "ARM": 0.60, "MU": 0.59, "SPY": 0.56,
    "IONQ": 0.74, "APLD": 0.75, "QQQ": 0.55, "AAPL": 0.55,
}

# Research / specialist engines that must drive confidence from generate()
# (binary gate-average would hard-cluster ~50–56% for every name).
_GENERATE_CONF_PREFIXES = (
    "v41", "v45", "v46", "v47", "v48", "v49", "v50", "v51",
    "v60", "v61", "v63", "v64", "v65", "v66", "v67",
    "v70", "v71", "v72", "v85",
)


def _resolve_model(model_arg: str, symbol: str | None = None) -> tuple[str, dict[str, Any]]:
    arg = (model_arg or equity_default_model()).strip()
    if arg in ("auto", "best"):
        rec = recommend_model(symbol)
        return rec["model"], rec
    if arg not in list_engine_models():
        raise SystemExit(
            f"Unknown model '{arg}'. Engines: {', '.join(list_engine_models())}"
        )
    return arg, {"model": arg, "reason": "user-selected"}


def _load_engine(model: str):
    if model in _ENGINE_CACHE:
        return _ENGINE_CACHE[model]
    path = engine_path(model)
    spec = importlib.util.spec_from_file_location(f"poc_va_{model}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load engine: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _ENGINE_CACHE[model] = mod
    return mod


def _resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Desk-local OHLCV resample — used when an engine module lacks the helper."""
    if not rule:
        return df
    cols = ["open", "high", "low", "close", "volume"]
    frame = df[[c for c in cols if c in df.columns]].copy()
    if "volume" not in frame.columns:
        frame["volume"] = 0.0
    return (
        frame.resample(rule, label="right", closed="right")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["close"])
    )


def _prior_session_profile_fallback(
    df: pd.DataFrame,
    lookback: int,
    rows: int,
    value_area_pct: float,
) -> dict[str, pd.Series]:
    """Minimal POC/VAH/VAL when engine has no _prior_session_profile."""
    idx = df.index
    nan = pd.Series(np.nan, index=idx)
    if df.empty or "close" not in df.columns:
        return {"poc": nan, "vah": nan, "val": nan}
    close = df["close"]
    lb = max(int(lookback), 5)
    poc = close.rolling(lb, min_periods=3).median()
    band = close.rolling(lb, min_periods=3).std().fillna(0.0) * 0.5
    _ = rows, value_area_pct
    return {"poc": poc, "vah": poc + band, "val": poc - band}


def _desk_mod_for_state(mod: Any, model_name: str) -> tuple[Any, str | None]:
    """Resolve module with equity desk helpers.

    Options wrappers (e.g. v35_softstruct_bag8) lack _resample_ohlcv; unwrap to
    their equity child so Analyze/Live still work when that model is selected.
    """
    if hasattr(mod, "_resample_ohlcv") and hasattr(mod, "_prior_session_profile"):
        return mod, None

    path_fn = getattr(mod, "_equity_engine_path", None)
    if callable(path_fn):
        try:
            eq_path = Path(path_fn())
            if eq_path.exists():
                key = f"_equity_from_{model_name}"
                if key in _ENGINE_CACHE:
                    return _ENGINE_CACHE[key], eq_path.parent.name
                spec = importlib.util.spec_from_file_location(f"poc_va_eq_{model_name}", eq_path)
                if spec is not None and spec.loader is not None:
                    eq_mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(eq_mod)
                    _ENGINE_CACHE[key] = eq_mod
                    return eq_mod, eq_path.parent.name
        except Exception:  # noqa: BLE001
            pass

    try:
        eng = mod.SignalEngine()
        eq = getattr(eng, "equity_engine", None)
        if eq is not None:
            eq_mod = sys.modules.get(type(eq).__module__)
            if eq_mod is not None and hasattr(eq_mod, "_resample_ohlcv"):
                return eq_mod, getattr(eq_mod, "__name__", None)
    except Exception:  # noqa: BLE001
        pass

    return mod, None


def _has_classic_desk_helpers(mod: Any) -> bool:
    return hasattr(mod, "_resample_ohlcv") and hasattr(mod, "_prior_session_profile")


def _engine_last_signal(
    mod: Any,
    code: str,
    frame: pd.DataFrame,
) -> tuple[float | None, str | None, float | None, str | None]:
    """Return latest (weight, error, confidence score, confidence kind).

    Newer research engines (v45+, v50/v71/v72, …) expose generate() rather than
    the classic VA/MACD helpers. Desk uses the last non-null target weight as the
    live long/flat decision. When the engine publishes ``last_confidence``, that
    value is returned as conf for live tickets (fail-soft: None if missing).
    """
    try:
        eng = mod.SignalEngine()
    except Exception as exc:  # noqa: BLE001
        return None, f"SignalEngine init failed: {exc}", None, None
    if not hasattr(eng, "generate"):
        return None, None, None, None
    confidence_kind = getattr(eng, "confidence_kind", None)

    yf = _to_yf(code)
    keys = [code, yf, f"{yf}.US"]
    # Unique preserve order
    seen: set[str] = set()
    data_map: dict[str, pd.DataFrame] = {}
    for k in keys:
        if k not in seen:
            data_map[k] = frame
            seen.add(k)

    try:
        out = eng.generate(data_map)
    except Exception as exc:  # noqa: BLE001
        return None, f"generate failed: {exc}", None, confidence_kind

    if not isinstance(out, dict):
        return None, "generate returned non-dict", None, confidence_kind

    sig = None
    used_key: str | None = None
    for k in keys:
        if k in out and out[k] is not None:
            sig = out[k]
            used_key = k
            break
    if sig is None and out:
        used_key = next(iter(out.keys()))
        sig = out[used_key]
    if sig is None:
        return None, "generate returned no series", None, confidence_kind

    conf_val: float | None = None
    raw_conf = getattr(eng, "last_confidence", None)
    if isinstance(raw_conf, dict) and raw_conf:
        conf_series = None
        for k in keys:
            if k in raw_conf and raw_conf[k] is not None:
                conf_series = raw_conf[k]
                break
        if conf_series is None:
            conf_series = next(iter(raw_conf.values()), None)
        if conf_series is not None:
            try:
                cs = pd.Series(conf_series).dropna()
                if not cs.empty:
                    conf_val = float(np.clip(float(cs.iloc[-1]), 0.0, 1.0))
            except Exception:  # noqa: BLE001
                conf_val = None

    try:
        s = pd.Series(sig).dropna()
        if s.empty:
            return 0.0, None, conf_val, confidence_kind
        return float(s.iloc[-1]), None, conf_val, confidence_kind
    except Exception as exc:  # noqa: BLE001
        return None, f"signal parse failed: {exc}", None, confidence_kind


def _fallback_kelly(conf: float, atr_pct: float, med_atr_pct: float, kelly_fraction: float = 0.5) -> float:
    if conf < 0.55 or not np.isfinite(conf):
        return 0.0
    if conf < 0.65:
        base = 0.35
    elif conf < 0.78:
        base = 0.65
    else:
        base = 1.0
    base *= float(np.clip(kelly_fraction / 0.5, 0.5, 1.0))
    vol_scale = float(np.clip(med_atr_pct / max(atr_pct, 1e-9), 0.4, 1.25))
    return float(np.clip(base * vol_scale, 0.25, 1.0))


def _to_yf(symbol: str) -> str:
    """Yahoo ticker. Applies desk aliases (INFQ→IONQ, GOOGL→GOOG)."""
    s = symbol.strip().upper()
    for suf in (".US", ".us"):
        if s.endswith(suf):
            s = s[: -len(suf)]
    try:
        from model_registry import resolve_desk_symbol  # local tools/

        code = resolve_desk_symbol(s)
        if code:
            return code.replace(".US", "")
    except Exception:
        pass
    return s


def _to_code(symbol: str) -> str:
    s = _to_yf(symbol)
    return f"{s}.US"


def _period_to_start(period: str) -> pd.Timestamp | None:
    """Map a yfinance-style period string to a cutoff timestamp. None means all."""
    if not period or period == "max":
        return None
    if period == "ytd":
        now = pd.Timestamp.now()
        return pd.Timestamp(now.year, 1, 1)
    m = re.match(r"^(\d+)(d|mo|y)$", period)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    now = pd.Timestamp.now()
    if unit == "d":
        return now - pd.Timedelta(days=n)
    if unit == "mo":
        return now - pd.DateOffset(months=n)
    if unit == "y":
        return now - pd.DateOffset(years=n)
    return None


def _load_cache(symbol: str, period: str, interval: str) -> pd.DataFrame | None:
    """Load OHLCV from repo data_cache as a fallback for yfinance."""
    if interval not in ("1h", "1d"):
        return None
    sym = _to_yf(symbol).split(".", 1)[0].upper()
    p = ROOT / "data_cache" / interval / f"{sym}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p).sort_index()
    except Exception:
        return None
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_convert(None)
    start = _period_to_start(period)
    if start is not None:
        df = df[df.index >= start]
    need = ["open", "high", "low", "close", "volume"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        return None
    df = df[need].copy()
    df = df.dropna(subset=["close"])
    return df if not df.empty else None


def _fetch_ohlcv(symbol: str, period: str = "60d", interval: str = "1h") -> pd.DataFrame:
    ysym = _to_yf(symbol)
    # Yahoo caps: 1m ≤ 7d, 5m/15m ≤ 60d
    if interval in ("1m", "2m") and period not in ("1d", "5d", "7d"):
        period = "5d"
    if interval in ("5m", "15m", "30m") and period in ("60d", "3mo", "6mo", "1y", "2y", "5y", "max"):
        period = "10d"
    raw = yf.download(ysym, period=period, interval=interval, auto_adjust=True, progress=False)
    if raw is None or raw.empty:
        cached = _load_cache(symbol, period, interval)
        if cached is not None:
            return cached
        raise ValueError(f"No data for {ysym}")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [c[0].lower() if isinstance(c, tuple) else str(c).lower() for c in raw.columns]
    else:
        raw.columns = [str(c).lower() for c in raw.columns]
    need = ["open", "high", "low", "close", "volume"]
    for c in need:
        if c not in raw.columns:
            cached = _load_cache(symbol, period, interval)
            if cached is not None:
                return cached
            raise ValueError(f"Missing column {c} for {ysym}")
    df = raw[need].copy()
    df.index = pd.to_datetime(df.index)
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    df = df.dropna(subset=["close"])
    if df.empty:
        cached = _load_cache(symbol, period, interval)
        if cached is not None:
            return cached
        raise ValueError(f"No data for {ysym}")
    return df


def _market_session() -> dict[str, Any]:
    """US equity session label in America/New_York."""
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/New_York"))
    except Exception:  # noqa: BLE001
        now = datetime.now(timezone.utc)
    mins = now.hour * 60 + now.minute
    wd = now.weekday()  # 0=Mon
    if wd >= 5:
        label, open_now = "WEEKEND", False
    elif mins < 4 * 60:
        label, open_now = "CLOSED", False
    elif mins < 9 * 60 + 30:
        label, open_now = "PRE-MARKET", False
    elif mins < 16 * 60:
        label, open_now = "RTH OPEN", True
    elif mins < 20 * 60:
        label, open_now = "AFTER-HOURS", False
    else:
        label, open_now = "CLOSED", False
    return {
        "label": label,
        "open": open_now,
        "et": now.strftime("%Y-%m-%d %H:%M:%S ET"),
        "weekday": now.strftime("%A"),
    }


def _compute_state(mod, code: str, df: pd.DataFrame, model_name: str, live: bool = False) -> dict[str, Any]:
    desk_mod, underlying = _desk_mod_for_state(mod, model_name)
    eng = desk_mod.SignalEngine()
    # routers expose _cfg(code); plain engines use defaults via __dict__/getattr
    if hasattr(eng, "_cfg"):
        cfg = eng._cfg(code)
    else:
        cfg = {k: getattr(eng, k) for k in dir(eng) if not k.startswith("_") and not callable(getattr(eng, k, None))}
        # common attrs
        for k in (
            "value_area_pct", "profile_rows", "profile_lookback", "macd_fast", "macd_slow",
            "macd_signal", "macd_htf", "signal_tf", "require_htf_green", "require_vwap_uptrend",
            "require_above_vwap", "require_volume_expand", "require_vol_confirm", "block_red_flag",
            "block_dump", "require_sqz_release", "require_mom_pos", "require_mom_pos_inc",
            "allow_healthy_pull_entry", "exit_on_poc_break", "exit_on_val_break", "exit_below_vwap",
            "exit_on_sqz_neg", "soft_confidence", "swing_period", "vol_look", "vol_sma",
            "min_confidence", "stop_atr", "trail_atr", "arm_trail_atr", "kelly_fraction",
        ):
            if hasattr(eng, k):
                cfg[k] = getattr(eng, k)

    # Live watch: keep native bar size (5m/1m) so open tape actually moves
    signal_tf = "" if live else (cfg.get("signal_tf", "2h") or "")
    resample_fn = getattr(desk_mod, "_resample_ohlcv", _resample_ohlcv)
    frame = resample_fn(df, signal_tf) if signal_tf else df
    if frame.empty:
        frame = df

    profile_lookback = int(cfg.get("profile_lookback", 20))
    profile_rows = int(cfg.get("profile_rows", 25))
    value_area_pct = float(cfg.get("value_area_pct", 0.7))
    macd_fast = int(cfg.get("macd_fast", 12))
    macd_slow = int(cfg.get("macd_slow", 26))
    macd_signal = int(cfg.get("macd_signal", 9))
    macd_htf = cfg.get("macd_htf", "4h")
    swing_period = int(cfg.get("swing_period", 50))
    vol_look = int(cfg.get("vol_look", 5))
    vol_sma = int(cfg.get("vol_sma", 20))
    stop_atr = float(cfg.get("stop_atr", 1.5))
    trail_atr = float(cfg.get("trail_atr", 2.5))
    arm_trail_atr = float(cfg.get("arm_trail_atr", 1.0))
    kelly_fraction = float(cfg.get("kelly_fraction", 0.5))
    min_confidence = float(cfg.get("min_confidence", 0.55))

    profile_fn = getattr(desk_mod, "_prior_session_profile", None)
    if callable(profile_fn):
        levels = profile_fn(frame, profile_lookback, profile_rows, value_area_pct)
    else:
        levels = _prior_session_profile_fallback(frame, profile_lookback, profile_rows, value_area_pct)
    close = frame["close"]
    high = frame["high"]
    low = frame["low"]
    poc, vah, val = levels["poc"], levels["vah"], levels["val"]
    poc_ok = (close >= poc) & poc.notna()
    in_va = (close >= val) & (close <= vah) & val.notna()
    # htf helper signatures differ slightly across versions
    if hasattr(desk_mod, "_htf_ha_green"):
        try:
            htf = desk_mod._htf_ha_green(frame, macd_htf, macd_fast, macd_slow, macd_signal)
        except TypeError:
            htf = desk_mod._htf_ha_green(
                frame, macd_htf, {"macd_fast": macd_fast, "macd_slow": macd_slow, "macd_signal": macd_signal}
            )
    else:
        htf = pd.Series(True, index=frame.index)
    if hasattr(desk_mod, "dynamic_swing_anchored_vwap"):
        swing = desk_mod.dynamic_swing_anchored_vwap(frame, swing_period)
    else:
        swing = pd.DataFrame({"vwap": close, "uptrend": True}, index=frame.index)
    vwap = swing["vwap"].shift(1)
    uptrend = swing["uptrend"].shift(1).fillna(False).astype(bool)
    above_vwap = (close >= vwap).fillna(False)
    if hasattr(desk_mod, "volume_price_state"):
        vp = desk_mod.volume_price_state(frame, vol_look, vol_sma)
    else:
        vp = pd.DataFrame({
            "confirm_up": True, "healthy_pull": False, "red_flag_up": False,
            "dump": False, "vol_expand": True,
        }, index=frame.index)
    if hasattr(desk_mod, "squeeze_momentum"):
        sqz = desk_mod.squeeze_momentum(frame)
    else:
        sqz = pd.DataFrame({
            "mom_pos": True, "mom_pos_inc": False, "mom_neg": False,
            "sqz_off": True, "sqz_release": False,
        }, index=frame.index)

    parts = {
        "poc_hold": poc_ok,
        "in_value_area": in_va,
        "htf_ha_green": htf,
        "vwap_uptrend": uptrend,
        "above_vwap": above_vwap,
        "vol_confirm_or_pull": vp["confirm_up"] | vp["healthy_pull"],
        "not_red_flag": ~vp["red_flag_up"],
        "mom_pos": sqz["mom_pos"],
        "sqz_off_or_release": sqz["sqz_off"] | sqz["sqz_release"],
    }
    conf = sum(p.astype(float) for p in parts.values()) / float(len(parts))

    prev_close = close.shift(1).fillna(close)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(span=14, adjust=False).mean()
    atr_pct = (atr / close.replace(0, np.nan)).fillna(0.0)
    med_atr_pct = float(atr_pct.replace(0, np.nan).median()) or 0.02

    gates = [poc_ok, in_va]
    if cfg.get("require_htf_green", True):
        gates.append(htf)
    if cfg.get("require_vwap_uptrend", False):
        gates.append(uptrend)
    if cfg.get("require_above_vwap", False):
        gates.append(above_vwap)
    if cfg.get("require_volume_expand", False):
        gates.append(vp["vol_expand"])
    if cfg.get("require_vol_confirm", False):
        gates.append(vp["confirm_up"] | (cfg.get("allow_healthy_pull_entry", False) & vp["healthy_pull"] & above_vwap))
    if cfg.get("block_red_flag", False):
        gates.append(~vp["red_flag_up"])
    if cfg.get("block_dump", False):
        gates.append(~vp["dump"])
    if cfg.get("require_sqz_release", False):
        gates.append(sqz["sqz_release"] | sqz["sqz_off"])
    if cfg.get("require_mom_pos", False):
        gates.append(sqz["mom_pos"])
    if cfg.get("require_mom_pos_inc", False):
        gates.append(sqz["mom_pos_inc"])
    long_hard = gates[0]
    for g in gates[1:]:
        long_hard = long_hard & g

    i = -1
    px = float(close.iloc[i])
    a = float(atr.iloc[i]) if np.isfinite(atr.iloc[i]) else px * 0.01
    c = float(conf.iloc[i])
    hard = bool(long_hard.iloc[i])
    kelly_fn = getattr(desk_mod, "_kelly_size", _fallback_kelly)
    sleeve = float(kelly_fn(c, float(atr_pct.iloc[i]), med_atr_pct, kelly_fraction))
    setup_ok = hard and c >= min_confidence and sleeve > 0

    part_flags = {k: bool(v.iloc[i]) for k, v in parts.items()}
    missing = [k for k, ok in part_flags.items() if not ok]

    # --- Generate-path engines (v45/v48–v51/v60/v61 and other research models) ---
    # Classic VA helpers still run for levels/structure overlays. When the model
    # exposes generate() and lacks full classic helpers, the live long/flat
    # decision comes from the last target weight.
    gen_signal: float | None = None
    gen_error: str | None = None
    gen_conf: float | None = None
    gen_conf_kind: str | None = None
    uses_classic = _has_classic_desk_helpers(desk_mod)
    is_generate_model = model_name.startswith(_GENERATE_CONF_PREFIXES) or (
        "spec_" in model_name or "router" in model_name or "bounce" in model_name
    )
    # Always try generate for non-classic OR specialist/research engines.
    # Specialists often also ship classic helpers — still prefer generate() DNA.
    should_try_generate = (not uses_classic) or is_generate_model
    size_frac = 0.0
    if should_try_generate:
        # Prefer original loaded module so wrappers keep their own generate()
        gen_mod = mod if hasattr(mod, "SignalEngine") else desk_mod
        gen_signal, gen_error, gen_conf, gen_conf_kind = _engine_last_signal(
            gen_mod, code, frame
        )
        if gen_signal is not None:
            gen_long = gen_signal > 1e-9
            # Target weight may be 0–1 (fraction) or ~0.2 (v50 scale) or 1.0 flat.
            size_raw = abs(float(gen_signal))
            size_frac = float(np.clip(size_raw if size_raw <= 1.5 else 1.0, 0.0, 1.5))
            if gen_long:
                setup_ok = True
                structure = float(np.clip(c, 0.0, 1.0))  # classic gate average as soft bonus
                if gen_conf is not None and np.isfinite(gen_conf) and float(gen_conf) > 0:
                    # Prefer engine-published entry confidence (v71/v72).
                    c = float(np.clip(0.55 * float(gen_conf) + 0.35 * min(size_frac, 1.0) + 0.10 * structure, 0.35, 0.96))
                else:
                    # Fallback: confidence from LIVE signal weight (legacy generate models).
                    # size 0.2 → ~0.50, size 0.5 → ~0.64, size 1.0 → ~0.88
                    c = float(
                        np.clip(
                            0.42 + 0.46 * min(size_frac, 1.0) + 0.10 * structure,
                            0.35,
                            0.95,
                        )
                    )
                sleeve = max(float(sleeve), max(0.20, min(1.0, size_frac if size_frac > 0 else 0.35)))
                hard = True
            else:
                # Flat specialist: keep STRUCTURE confidence so pullback/breakout
                # watch kinds can still fire with real levels. Do NOT crush to ~30%
                # (that made every non-CRWV specialist look broken with no plan).
                structure = float(np.clip(c, 0.0, 1.0))
                if gen_conf is not None and np.isfinite(gen_conf) and float(gen_conf) > 0:
                    c = float(np.clip(0.25 * float(gen_conf) + 0.55 * structure, 0.22, 0.80))
                else:
                    c = float(np.clip(0.28 + 0.52 * structure, 0.22, 0.78))
                if not uses_classic or is_generate_model:
                    setup_ok = False
                    hard = False

    # Historical prior only when real evidence exists (model+symbol or symbol bag).
    # Default used to be hard-coded 0.55 → every specialist collapsed near 56%.
    hist_wr = hist_win_rate(model_name, code)
    symbol_prior = _PRIOR_WR.get(_to_yf(code))
    if hist_wr is not None:
        prior = float(hist_wr)
        prior_source = "model_symbol_hist_wr"
    elif symbol_prior is not None and not is_generate_model:
        prior = float(symbol_prior)
        prior_source = "symbol_bag_prior"
    else:
        prior = None
        prior_source = "none_live_only"

    # conf_prob maps structural/live c into a probability-like band
    conf_prob = float(np.clip(0.20 + c * 0.70, 0.15, 0.95))
    if prior is not None:
        # Light prior blend — live structure still dominates (70/30)
        hit_prob = float(np.clip(0.70 * conf_prob + 0.30 * prior, 0.15, 0.92))
    else:
        hit_prob = conf_prob

    stop = px - stop_atr * a
    arm = px + arm_trail_atr * a
    trail_dist = trail_atr * a
    atr_i = a if a > 0 else px * 0.01

    # --- Structure: VOLUME first, then EMA22 (drawdowns), EMA200 (regime) ---
    # Sector rotation = which pond. Volume + EMAs = when to cast.
    ema22 = close.ewm(span=22, adjust=False).mean()
    ema200 = close.ewm(span=200, adjust=False).mean()
    e22 = float(ema22.iloc[i])
    e200 = float(ema200.iloc[i]) if len(close) >= 180 and np.isfinite(ema200.iloc[i]) else None
    above_22 = bool(np.isfinite(e22) and px >= e22)
    above_200 = True if e200 is None else bool(px >= e200)
    lost_200 = e200 is not None and not above_200
    dist_22_atr = (px - e22) / atr_i if np.isfinite(e22) else 0.0
    # Healthy drawdown: tagging 22 EMA from above while 200 structure intact
    near_22_pull = above_200 and (-0.15 <= dist_22_atr <= 0.55)
    reclaim_200 = False
    if e200 is not None and len(close) > 2:
        prev_below = float(close.iloc[i - 1]) < float(ema200.iloc[i - 1])
        reclaim_200 = (not lost_200) and prev_below

    vol = frame["volume"]
    vol_sma20 = vol.rolling(20, min_periods=5).mean()
    vs = float(vol_sma20.iloc[i]) if np.isfinite(vol_sma20.iloc[i]) and float(vol_sma20.iloc[i]) > 0 else 1.0
    rvol = float(vol.iloc[i]) / vs
    vol_rising = bool(float(vol.iloc[i]) > float(vol.iloc[i - 5])) if len(vol) > 5 else False
    vol_expand = bool(vp["vol_expand"].iloc[i])
    vol_confirm = bool(vp["confirm_up"].iloc[i])
    vol_dry = bool(vp["red_flag_up"].iloc[i]) or (rvol < 0.75 and not vol_rising)
    vol_awake = (rvol >= 1.0) or vol_expand or vol_rising or vol_confirm
    # Real breakouts are volume events — price follows participation
    vol_surge = (rvol >= 1.35) or (vol_expand and vol_rising) or (vol_confirm and rvol >= 1.1)
    healthy_dip_vol = bool(vp["healthy_pull"].iloc[i])

    hh20 = float(high.rolling(20, min_periods=5).max().iloc[i])
    dist_high_atr = (hh20 - px) / atr_i
    pressing_high = dist_high_atr <= 0.45
    vah_v = float(vah.iloc[i]) if np.isfinite(vah.iloc[i]) else None
    near_vah = False
    just_broke_vah = False
    if vah_v is not None and vah_v > 0:
        near_vah = (px >= vah_v * 0.982) and (px <= vah_v * 1.008)
        just_broke_vah = (px > vah_v) and (px <= vah_v + 0.85 * atr_i)
    coiling = float(atr_pct.iloc[i]) < med_atr_pct * 0.92
    sqz_ready = bool(sqz["sqz_release"].iloc[i] or sqz["sqz_off"].iloc[i] or sqz["mom_pos"].iloc[i])
    trend_ok = bool(htf.iloc[i]) and bool(above_vwap.iloc[i]) and bool(part_flags.get("not_red_flag", True))
    structure_ok = bool(part_flags.get("poc_hold", False)) or pressing_high

    breakout_buy = (
        above_200
        and not vol_dry
        and vol_surge  # PRIMARY gate
        and (just_broke_vah or pressing_high)
        and bool(sqz["mom_pos"].iloc[i])
        and trend_ok
        and c >= 0.55
    )
    breakout_ready = (
        (not breakout_buy)
        and above_200
        and not vol_dry
        and vol_awake
        and structure_ok
        and (pressing_high or near_vah or (coiling and (near_vah or pressing_high)))
        and sqz_ready
        and trend_ok
        and c >= 0.50
    )
    pullback_to_22 = (
        (not setup_ok)
        and near_22_pull
        and above_200
        and trend_ok
        and c >= 0.58
        and (healthy_dip_vol or "in_value_area" in missing)
    )

    if breakout_buy:
        sleeve = max(float(sleeve), 0.35) * 0.75

    # Lost 200 EMA = structural break; only volume-led reclaim is an exception
    if lost_200 and not (reclaim_200 and vol_surge) and gen_signal is None:
        setup_kind = "structural_break"
    elif gen_signal is not None and gen_signal > 1e-9:
        setup_kind = "classic_buy"
    elif gen_signal is not None and gen_signal <= 1e-9 and not uses_classic:
        setup_kind = "wait"
    elif setup_ok and (above_200 or e200 is None):
        setup_kind = "classic_buy"
    elif breakout_buy:
        setup_kind = "breakout_buy"
    elif breakout_ready:
        setup_kind = "breakout_watch"
    elif pullback_to_22 or ("in_value_area" in missing and c >= 0.60 and trend_ok and above_200):
        setup_kind = "pullback_watch"
    # Hard AVOID only on red-flag traps. Dry volume alone is WAIT so the
    # scan still surfaces levels (breakout / dip) instead of a wall of AVOID.
    elif not part_flags.get("not_red_flag", True):
        setup_kind = "avoid"
    elif vol_dry and not (pressing_high or near_22_pull or structure_ok or near_vah):
        setup_kind = "avoid"
    else:
        setup_kind = "wait"

    if setup_kind == "structural_break":
        hit_prob = float(np.clip(hit_prob - 0.12, 0.12, 0.55))
    elif setup_kind not in ("classic_buy", "breakout_buy"):
        # Soft penalty for wait — was clamping everything into 35–70% → looked like 56%.
        hit_prob = float(np.clip(hit_prob - 0.06, 0.12, 0.75))
    elif setup_kind == "breakout_buy":
        hit_prob = float(np.clip(hit_prob - 0.03, 0.30, 0.90))

    breakout_level = None
    if np.isfinite(hh20) and (just_broke_vah or (vah_v is not None and px >= vah_v) or pressing_high):
        breakout_level = round(hh20, 4)
    elif vah_v is not None:
        breakout_level = round(vah_v, 4)
    elif np.isfinite(hh20):
        breakout_level = round(hh20, 4)

    part_flags = {
        **part_flags,
        "vol_surge": vol_surge,
        "vol_awake": vol_awake,
        "not_vol_dry": not vol_dry,
        "above_ema22": above_22,
        "above_ema200": above_200,
        "near_ema22": near_22_pull,
    }

    return {
        "model": model_name,
        "desk_engine": underlying or model_name,
        "engine_kind": engine_kind(model_name),
        "symbol": _to_yf(code),
        "code": code,
        "asof": str(frame.index[i]),
        "interval": signal_tf or "1h",
        "htf": macd_htf,
        "price": round(px, 4),
        "atr": round(a, 4),
        "poc": None if not np.isfinite(poc.iloc[i]) else round(float(poc.iloc[i]), 4),
        "val": None if not np.isfinite(val.iloc[i]) else round(float(val.iloc[i]), 4),
        "vah": None if not np.isfinite(vah.iloc[i]) else round(float(vah.iloc[i]), 4),
        "vwap": None if not np.isfinite(vwap.iloc[i]) else round(float(vwap.iloc[i]), 4),
        "ema22": round(e22, 4) if np.isfinite(e22) else None,
        "ema200": round(e200, 4) if e200 is not None else None,
        "rvol": round(rvol, 2),
        "vol_surge": vol_surge,
        "vol_awake": vol_awake,
        "vol_dry": vol_dry,
        "above_ema22": above_22,
        "above_ema200": above_200,
        "near_ema22": near_22_pull,
        "lost_200": lost_200,
        "reclaim_200": reclaim_200,
        "confidence": round(c, 3),
        "min_confidence": min_confidence,
        "setup_ok": setup_kind in ("classic_buy", "breakout_buy"),
        "setup_kind": setup_kind,
        "breakout_ready": breakout_ready,
        "breakout_buy": breakout_buy,
        "breakout_level": breakout_level,
        "pressing_high": pressing_high,
        "coiling": coiling,
        "hard_gates_ok": hard,
        "sleeve_fraction": round(float(sleeve), 3),
        "hit_probability": round(hit_prob, 3),
        "hit_probability_kind": "heuristic_probability_like_score_not_calibrated",
        "prior_wr": prior,
        "prior_source": prior_source,
        "gen_signal": None if gen_signal is None else round(float(gen_signal), 4),
        "engine_confidence": None if gen_conf is None else round(float(gen_conf), 4),
        "engine_confidence_kind": gen_conf_kind,
        "confidence_kind": gen_conf_kind or "heuristic_probability_like_score_not_calibrated",
        "confidence_source": (
            "engine_last_confidence"
            if (gen_conf is not None and gen_signal is not None and float(gen_signal) > 1e-9)
            else (
                "generate_signal"
                if (gen_signal is not None and is_generate_model)
                else "classic_gate_average"
            )
        ),
        "flags": part_flags,
        "missing": missing,
        "entry": round(px, 4) if setup_kind in ("classic_buy", "breakout_buy") else None,
        "stop": round(stop, 4),
        "stop_atr_mult": stop_atr,
        "trail_arm": round(arm, 4),
        "trail_atr_mult": trail_atr,
        "trail_distance": round(trail_dist, 4),
        "risk_per_share": round(max(px - stop, 0.01), 4),
        "generate_signal": None if gen_signal is None else round(float(gen_signal), 4),
        "generate_error": gen_error,
        "signal_path": (
            "generate"
            if gen_signal is not None
            else ("classic" if uses_classic else "classic_fallback")
        ),
        "routing_notes": {
            "require_mom_pos": bool(cfg.get("require_mom_pos", False)),
            "require_above_vwap": bool(cfg.get("require_above_vwap", False)),
            "exit_below_vwap": bool(cfg.get("exit_below_vwap", False)),
            "block_red_flag": bool(cfg.get("block_red_flag", False)),
            "generate_driven": gen_signal is not None,
        },
    }


def _position_math(state: dict, account: float, risk_pct: float) -> dict[str, Any]:
    risk_budget = account * risk_pct
    rps = float(state["risk_per_share"])
    shares_by_risk = int(risk_budget // rps) if rps > 0 else 0
    # sleeve caps notional
    sleeve = float(state["sleeve_fraction"])
    # Live adapt: paper/IB closed trades scale next size (persistent runs/live_adapt)
    adapt_mult = 1.0
    try:
        import live_adapt as _la

        adapt_mult = float(
            _la.size_mult_for(
                str(state.get("model") or state.get("desk_engine") or ""),
                str(state.get("symbol") or ""),
            )
        )
        sleeve = max(0.15, min(1.5, sleeve * adapt_mult))
    except Exception:
        adapt_mult = 1.0
    max_notional = account * sleeve if sleeve > 0 else 0.0
    px = float(state["price"])
    shares_by_sleeve = int(max_notional // px) if px > 0 else 0
    shares = min(shares_by_risk, shares_by_sleeve) if state["setup_ok"] else 0
    if not state["setup_ok"]:
        # still show what risk would look like IF you forced entry
        shares = min(shares_by_risk, int((account * max(sleeve, 0.25)) // px)) if px > 0 else 0
        forced = True
    else:
        forced = False
    notional = shares * px
    dollar_risk = shares * rps
    # Reward proxy: trail arm distance as first target
    # state["entry"] is always None or == px today (see _compute_state), so
    # this is currently equivalent to basis=px; the floor removal is what
    # actually changes behavior below.
    basis = float(state.get("entry") or px)
    reward = float(state["trail_arm"]) - basis  # no floor: a bad setup shows its true R:R
    rr = reward / rps if rps > 0 else 0.0
    return {
        "account": account,
        "risk_pct": risk_pct,
        "risk_budget": round(risk_budget, 2),
        "shares": shares,
        "notional": round(notional, 2),
        "dollar_risk": round(dollar_risk, 2),
        "reward_to_arm": round(reward, 4),
        "rr_to_arm": round(rr, 2),
        "forced_preview": forced,
        "live_adapt_mult": round(adapt_mult, 4),
        "sleeve_after_adapt": round(sleeve, 4),
    }


def analyze(
    symbol: str,
    account: float,
    risk_pct: float,
    period: str = "60d",
    model: str | None = None,
    interval: str = "1h",
    live: bool = False,
    ranks: bool = True,
) -> dict[str, Any]:
    model_name, selection = _resolve_model(model or equity_default_model(), symbol)
    mod = _load_engine(model_name)
    code = _to_code(symbol)
    if live:
        interval = interval or "5m"
        if period in ("60d", ""):
            period = "10d" if interval != "1m" else "5d"
    df = _fetch_ohlcv(symbol, period=period, interval=interval)
    state = _compute_state(mod, code, df, model_name, live=live)
    state["data_interval"] = interval
    state["live"] = live
    sizing = _position_math(state, account, risk_pct)
    plan = _plain_plan(state)
    symbol_ranks = rank_models_for_symbol(symbol, engines_only=False)[:8] if ranks else []
    return {
        "model": model_name,
        "model_selection": selection,
        "state": state,
        "plan": plan,
        "sizing": sizing,
        "model_ranks_for_symbol": symbol_ranks,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _snapshot_row(out: dict[str, Any]) -> dict[str, Any]:
    st, plan = out["state"], _plain_plan(out["state"])
    return {
        "symbol": st["symbol"],
        "action": plan["action"],
        "why": plan["why"],
        "do_next": plan["do_next"],
        "setup_kind": st.get("setup_kind"),
        "price": st["price"],
        "stop": st["stop"],
        "rvol": st.get("rvol"),
        "vol_surge": st.get("vol_surge"),
        "vol_dry": st.get("vol_dry"),
        "ema22": st.get("ema22"),
        "ema200": st.get("ema200"),
        "above_ema22": st.get("above_ema22"),
        "above_ema200": st.get("above_ema200"),
        "near_ema22": st.get("near_ema22"),
        "breakout_level": st.get("breakout_level"),
        "confidence": st["confidence"],
        "asof": st.get("asof"),
        "interval": st.get("data_interval", "1h"),
    }


def _print_watch_board(
    rows: list[dict[str, Any]],
    prev: dict[str, dict],
    session: dict[str, Any],
    every: int,
    tick: int,
) -> None:
    print()
    print("=" * 78)
    print(f"  LIVE WATCH  ·  {session['et']}  ·  {session['label']}  ·  tick #{tick}  ·  every {every}s")
    print("  Ctrl+C to stop  ·  Yahoo delay ~1–15m (not a broker feed)")
    print("=" * 78)
    print(
        f"  {'SYM':<6} {'ACTION':<26} {'PX':>9} {'Δ':>7} {'RVOL':>6} "
        f"{'22':>5} {'200':>5}  NOTE"
    )
    alerts: list[str] = []
    for r in rows:
        sym = r["symbol"]
        p = prev.get(sym)
        px_d = ""
        if p and p.get("price") is not None:
            d = float(r["price"]) - float(p["price"])
            px_d = f"{d:+.2f}" if abs(d) >= 0.005 else ""
        act_chg = ""
        if p and p.get("action") != r["action"]:
            act_chg = " ★"
            alerts.append(f"{sym}: {p.get('action')} → {r['action']}")
        e22 = "Y" if r.get("above_ema22") else "n"
        e200 = "Y" if r.get("above_ema200") else "N"
        if r.get("near_ema22"):
            e22 = "~"
        rv = r.get("rvol")
        rv_s = f"{rv:.1f}x" if rv is not None else "—"
        if r.get("vol_surge"):
            rv_s += "!"
        elif r.get("vol_dry"):
            rv_s += "↓"
        note = ""
        if "BREAKOUT" in r["action"] or "BUY" in r["action"]:
            note = (r.get("do_next") or "")[:28]
        elif "structure" in r["action"].lower():
            note = "lost 200 EMA"
        elif r.get("near_ema22"):
            note = "near 22 EMA"
        print(
            f"  {sym:<6} {(r['action'] + act_chg):<26} "
            f"${r['price']:>8.2f} {px_d:>7} {rv_s:>6} "
            f"{e22:>5} {e200:>5}  {note}"
        )
    if alerts:
        print("-" * 78)
        print("  CHANGES THIS TICK")
        for a in alerts:
            print(f"    ★ {a}")
    print("-" * 78)
    print("  Volume first · 22 EMA = drawdowns · 200 EMA = structure · sector rotate = pond")
    print("=" * 78)
    print()


def run_watch(
    symbols: list[str],
    account: float,
    risk_pct: float,
    model: str,
    every: int = 30,
    interval: str = "5m",
    clear: bool = True,
    max_ticks: int | None = None,
) -> int:
    """Refresh board until Ctrl+C. Built for market-open tape watching."""
    every = max(15, int(every))
    prev: dict[str, dict] = {}
    tick = 0
    print(
        f"Starting live watch on {', '.join(symbols)}  "
        f"(interval={interval}, refresh={every}s). Ctrl+C to stop.",
        flush=True,
    )
    try:
        while True:
            tick += 1
            session = _market_session()
            rows: list[dict[str, Any]] = []
            errors: list[str] = []
            for sym in symbols:
                try:
                    out = analyze(
                        sym, account, risk_pct,
                        model=model, interval=interval, live=True, ranks=False,
                    )
                    rows.append(_snapshot_row(out))
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{sym}: {exc}")
            if clear and tick > 1:
                # ANSI clear — works in most terminals
                print("\033[2J\033[H", end="", flush=True)
            _print_watch_board(rows, prev, session, every, tick)
            if errors:
                print("  Fetch issues:")
                for e in errors[:6]:
                    print(f"    ! {e}")
                print()
            # single-name deep dive when only one symbol
            if len(rows) == 1 and not errors:
                r = rows[0]
                print(f"  {r['symbol']} detail: {r['why']}")
                print(f"  → {r['do_next']}")
                if r.get("breakout_level"):
                    print(f"  Breakout level ${r['breakout_level']:.2f}  |  bar asof {r.get('asof')}")
                print()
            prev = {r["symbol"]: r for r in rows}
            if max_ticks is not None and tick >= max_ticks:
                return 0
            # near open: hint if still closed
            if session["label"] == "PRE-MARKET" and tick == 1:
                print("  Pre-market: tape is thin — volume signals are noisier until 9:30 ET.\n")
            time.sleep(every)
    except KeyboardInterrupt:
        print("\n  Watch stopped.\n")
        return 0


def scan_picks(
    symbols: list[str],
    account: float,
    risk_pct: float,
    horizon: str,
    model: str = DEFAULT_MODEL,
) -> list[dict[str, Any]]:
    rows = []
    # Skip per-symbol rank tables during scan (O(symbols × models)); use recommend once.
    want_auto = (model or "").strip() in ("auto", "best", "")
    for sym in symbols:
        try:
            out = analyze(sym, account, risk_pct, model=model, ranks=False)
            st, sz = out["state"], out["sizing"]
            kind = st.get("setup_kind") or ("classic_buy" if st["setup_ok"] else "wait")
            kind_mult = {
                "classic_buy": 1.0,
                "breakout_buy": 0.90,  # volume-confirmed breakout
                "breakout_watch": 0.58,
                "pullback_watch": 0.48,  # 22 EMA / value dip
                "wait": 0.28,
                "avoid": 0.10,
                "structural_break": 0.05,
            }.get(kind, 0.30)
            score = st["hit_probability"] * kind_mult * max(st["sleeve_fraction"], 0.25)
            if horizon == "week":
                score *= (1.05 if st["flags"].get("mom_pos") else 0.9)
                score *= (1.05 if st["flags"].get("htf_ha_green") else 0.85)
            # Volume is the main precipitor — boost / cut score by participation
            if st.get("vol_surge"):
                score *= 1.15
            elif st.get("vol_dry"):
                score *= 0.70
            if st.get("near_ema22") and st.get("above_ema200"):
                score *= 1.06
            if st.get("lost_200"):
                score *= 0.40
            if st.get("pressing_high") or st.get("breakout_ready"):
                score *= 1.05
            if want_auto:
                best = out.get("model_selection") or recommend_model(sym)
            else:
                best = recommend_model(sym)
            plan = _plain_plan(st)
            rows.append({
                "symbol": st["symbol"],
                "sector": _symbol_sector(sym),
                "model": out["model"],
                "best_hist_model": best.get("model"),
                "best_hist_score": best.get("score"),
                "setup_ok": st["setup_ok"],
                "setup_kind": kind,
                "breakout_level": st.get("breakout_level"),
                "pressing_high": st.get("pressing_high"),
                "rvol": st.get("rvol"),
                "vol_surge": st.get("vol_surge"),
                "ema22": st.get("ema22"),
                "ema200": st.get("ema200"),
                "above_ema200": st.get("above_ema200"),
                "price": st["price"],
                "entry": st["entry"],
                "stop": st["stop"],
                "confidence": st["confidence"],
                "hit_probability": st["hit_probability"],
                "sleeve": st["sleeve_fraction"],
                "shares": sz["shares"],
                "dollar_risk": sz["dollar_risk"],
                "rr_to_arm": sz["rr_to_arm"],
                "missing": st["missing"][:3],
                "action": plan["action"],
                "do_next": plan["do_next"],
                "score": round(score, 4),
            })
        except Exception as exc:  # noqa: BLE001
            rows.append({"symbol": _to_yf(sym), "error": str(exc), "score": -1, "setup_ok": False})
    rows.sort(key=lambda r: r.get("score", -1), reverse=True)
    return rows


_FLAG_LABELS = {
    "poc_hold": "Holding above POC (support)",
    "in_value_area": "Inside value area (not chasing)",
    "htf_ha_green": "Bigger-timeframe trend is up",
    "vwap_uptrend": "VWAP trend is up",
    "above_vwap": "Price is above VWAP",
    "vol_confirm_or_pull": "Volume confirms the move",
    "not_red_flag": "Not a weak rally (vol drying up)",
    "mom_pos": "Momentum is positive",
    "sqz_off_or_release": "Squeeze released / not crushed",
    "vol_surge": "Volume SURGE (breakout fuel)",
    "vol_awake": "Volume waking vs average",
    "not_vol_dry": "Volume not drying on the push",
    "above_ema22": "Above 22 EMA (drawdown support)",
    "above_ema200": "Above 200 EMA (structure intact)",
    "near_ema22": "Near 22 EMA (pullback zone)",
}

_MISSING_DO = {
    "in_value_area": "Do NOT buy here — price is extended above the value area. Wait for a pullback toward VAH/VAL.",
    "poc_hold": "Do NOT buy — price lost POC support. Wait for a reclaim of POC.",
    "htf_ha_green": "Do NOT buy — bigger-timeframe trend is not green yet. Wait for HTF flip up.",
    "vwap_uptrend": "Wait for VWAP to turn up (or skip if your model requires it).",
    "above_vwap": "Wait for price to get back above VWAP before entry.",
    "vol_confirm_or_pull": "Wait for volume to expand with price (or a quiet healthy pullback).",
    "not_red_flag": "AVOID for now — price rising on dying volume (trap risk).",
    "mom_pos": "Wait for momentum to turn positive.",
    "sqz_off_or_release": "Wait for squeeze release / momentum expansion.",
}


def _plain_plan(state: dict) -> dict[str, Any]:
    """Turn gates into a simple action a human can follow."""
    missing = list(state.get("missing") or [])
    flags = state.get("flags") or {}
    conf = float(state.get("confidence") or 0)
    kind = state.get("setup_kind") or ("classic_buy" if state.get("setup_ok") else "wait")
    lvl = state.get("breakout_level")
    vah = state.get("vah")
    val = state.get("val")
    e22 = state.get("ema22")
    e200 = state.get("ema200")
    rvol = state.get("rvol")

    if kind == "structural_break":
        action = "AVOID (structure broken)"
        why = (
            f"Lost the 200 EMA"
            + (f" (${e200:.2f})" if e200 else "")
            + " — structural break. Don't buy dips until volume reclaims it."
        )
        do_next = (
            f"Stand aside. Watch for a volume surge reclaim of the 200"
            + (f" (${e200:.2f})" if e200 else "")
            + ". Until then, longs are fighting broken structure."
        )
    elif kind == "classic_buy":
        action = "BUY NOW"
        if state.get("near_ema22") and e22:
            why = f"Pullback into the 22 EMA (~${e22:.2f}) with structure intact — best R:R flavor."
        else:
            why = "Pullback-in-value setup is live. Use the size/stop below."
        do_next = (
            f"Buy around ${state['price']:.2f}. "
            f"Hard stop ${state['stop']:.2f}. "
            f"If it runs to ${state['trail_arm']:.2f}, trail under the high."
        )
    elif kind == "breakout_buy":
        action = "BUY BREAKOUT"
        why = (
            f"Volume-led breakout"
            + (f" (rvol {rvol:.1f}x)" if rvol else "")
            + " — participation confirms the move. Smaller size."
        )
        do_next = (
            f"Buy around ${state['price']:.2f} (½–¾ normal size). "
            f"Stop ${state['stop']:.2f}. "
            f"Invalid if it fails back under {f'${lvl:.2f}' if lvl else 'breakout level'} "
            f"or volume dies."
        )
    elif kind == "breakout_watch":
        action = "BREAKOUT WATCH"
        why = "Near highs with volume waking — breakout precipitates when volume SURGES through the level."
        trigger = f"${lvl:.2f}" if lvl else "the 20-bar high"
        px = float(state.get("price") or 0)
        if lvl and px >= float(lvl) * 0.998:
            do_next = (
                f"Already pressing ${px:.2f}. Only buy on a VOLUME push through {trigger} "
                f"(rvol ≥ ~1.3x). Abort under ${state['stop']:.2f}."
            )
        else:
            do_next = (
                f"Alert above {trigger}. Enter only when volume expands with the break; "
                f"ignore a quiet drift through. Stop under ${state['stop']:.2f}."
            )
    elif kind == "pullback_watch":
        action = "PULLBACK ZONE"
        if state.get("near_ema22") and e22:
            why = f"Trend OK — wait for / buy the dip into the 22 EMA (~${e22:.2f}), not the extension."
            do_next = (
                f"Alert near 22 EMA ${e22:.2f}"
                + (f" / VAL ${val:.2f}" if val else "")
                + ". Prefer quiet volume on the dip (healthy), then buy when volume returns up."
            )
        else:
            why = "Trend is fine but price is chasing above value — wait for a dip."
            if vah is not None and val is not None:
                do_next = (
                    f"Alert near VAH ${vah:.2f} or VAL ${val:.2f}"
                    + (f" / 22 EMA ${e22:.2f}" if e22 else "")
                    + f". Don't chase ${state['price']:.2f}."
                )
            else:
                do_next = _MISSING_DO["in_value_area"]
    elif kind == "avoid" or not flags.get("not_red_flag", True):
        # Hard AVOID only for red-flag traps / explicit avoid kind.
        # Dry volume alone is WAIT so the board still surfaces levels.
        action = "AVOID"
        why = "Weak tape: price push on dying volume — classic trap. Volume is the veto."
        do_next = "Stand aside until volume confirms (rvol > 1) or price resets into value / 22 EMA."
    elif state.get("vol_dry"):
        action = "WAIT"
        rvol_s = f"{rvol:.1f}x" if rvol is not None else "quiet"
        why = (
            f"Volume quiet ({rvol_s}) · structure readiness {conf:.0%} — "
            "not a veto; wait for participation before sizing."
        )
        bits = []
        if e22:
            bits.append(f"dip zone ~22 EMA ${e22:.2f}")
        if val:
            bits.append(f"demand/VAL ${val:.2f}")
        if lvl:
            bits.append(f"volume break ${lvl:.2f}")
        do_next = (
            ("Watch: " + " · ".join(bits[:3]) + ". Enter only when rvol expands.")
            if bits
            else "Stand aside until rvol > 1 or price resets into value / 22 EMA."
        )
    elif "poc_hold" in missing:
        action = "WAIT"
        why = "Support (POC) is broken."
        do_next = _MISSING_DO["poc_hold"]
    elif len(missing) <= 2 and conf >= 0.65:
        action = "WAIT (almost ready)"
        why = f"Only {len(missing)} check(s) left — close, but not a green light yet."
        do_next = " ".join(_MISSING_DO.get(m, m) for m in missing[:2])
    else:
        # Operator English with levels — never "several conditions are off" alone.
        action = "WAIT"
        off = [ _FLAG_LABELS.get(m, m) for m in missing[:3] ]
        off_s = "; ".join(off) if off else "entry score not ready"
        why = (
            f"No long entry yet · structure readiness {conf:.0%}. "
            f"Still off: {off_s}."
        )
        bits = []
        if e22:
            bits.append(f"dip-buy zone ~22 EMA ${e22:.2f}")
        if val:
            bits.append(f"demand/VAL ${val:.2f}")
        if lvl:
            bits.append(f"break only on volume through ${lvl:.2f}")
        if e200:
            bits.append(f"invalid if lose 200 EMA ${e200:.2f} on volume")
        if bits:
            do_next = "Watch: " + " · ".join(bits[:3]) + ". Stand aside until one path prints."
        else:
            do_next = (
                " ".join(_MISSING_DO.get(m, m) for m in missing[:3])
                if missing
                else "Re-check later — no clean level map yet."
            )

    checklist = [
        {"ok": bool(flags.get(k)), "label": _FLAG_LABELS.get(k, k), "key": k}
        for k in _FLAG_LABELS
    ]
    gen_sig = state.get("generate_signal")
    conf_note = (
        f"Confidence {conf:.0%} = live structure readiness"
        + (f" · specialist size {float(gen_sig):.2f}" if gen_sig not in (None, 0, 0.0) else " · specialist flat")
        + ". Breakouts need VOLUME; 22 EMA = dip zone; lost 200 EMA = structural break."
    )
    return {
        "action": action,
        "why": why,
        "do_next": do_next,
        "checklist": checklist,
        "confidence_note": conf_note,
    }


def _print_analyze(payload: dict) -> None:
    st, sz = payload["state"], payload["sizing"]
    plan = _plain_plan(st)
    sel = payload.get("model_selection") or {}

    print()
    print("=" * 64)
    print(f"  {st['symbol']}   >>>  {plan['action']}  <<<")
    print("=" * 64)
    print(f"  Why:     {plan['why']}")
    print(f"  Do this: {plan['do_next']}")
    print(f"  Model:   {payload.get('model')}  ({sel.get('reason', 'selected')})")
    print(f"  Time:    {st['asof']}")
    print("-" * 64)
    print("  NUMBERS")
    print(f"    Price now     ${st['price']:.2f}")
    print(f"    Confidence    {st['confidence']:.0%}   ← {plan['confidence_note']}")
    print(f"    Chance (est.) {st['hit_probability']:.0%}   based on this model’s past win-rate + live checks")
    if plan["action"] in ("BUY NOW", "BUY BREAKOUT"):
        print(f"    Buy around    ${st['entry']:.2f}")
        print(f"    Stop loss     ${st['stop']:.2f}  (about ${st['risk_per_share']:.2f}/share)")
        print(f"    First target  ${st['trail_arm']:.2f} then trail winners")
        print(f"    Shares        {sz['shares']}   (~${sz['notional']:,.0f})")
        print(f"    Cash at risk  ${sz['dollar_risk']:,.2f}  ({sz['risk_pct']:.0%} of ${sz['account']:,.0f})")
        if plan["action"] == "BUY BREAKOUT":
            print("    Note          Breakout size is smaller (½–¾ sleeve)")
    else:
        print(f"    If you forced it anyway (don't): stop ${st['stop']:.2f}, preview {sz['shares']} sh / ${sz['dollar_risk']:.0f} risk")
        if st.get("val") is not None and st.get("vah") is not None:
            print(f"    Value zone    ${st['val']:.2f}  →  ${st['vah']:.2f}   (POC ${st.get('poc')})")
        if st.get("breakout_level") is not None:
            print(f"    Breakout lvl  ${st['breakout_level']:.2f}   (buy-stop / alert)")
        if st.get("vwap") is not None:
            print(f"    VWAP          ${st['vwap']:.2f}")
    # Always show structure stack (volume + EMAs)
    print("-" * 64)
    print("  STRUCTURE  (volume first → then EMAs)")
    rvol = st.get("rvol")
    vol_note = "SURGE" if st.get("vol_surge") else ("awake" if st.get("vol_awake") else ("DRY" if st.get("vol_dry") else "quiet"))
    print(f"    Volume        rvol {rvol:.1f}x  [{vol_note}]" if rvol is not None else f"    Volume        [{vol_note}]")
    if st.get("ema22") is not None:
        tag22 = "holding" if st.get("above_ema22") else "LOST"
        near = " ← pullback zone" if st.get("near_ema22") else ""
        print(f"    22 EMA        ${st['ema22']:.2f}  [{tag22}]{near}")
    if st.get("ema200") is not None:
        tag200 = "intact" if st.get("above_ema200") else "BROKEN"
        print(f"    200 EMA       ${st['ema200']:.2f}  [{tag200}]")
    print("-" * 64)
    print("  CHECKLIST  (green = good)")
    for row in plan["checklist"]:
        mark = "YES" if row["ok"] else "NO "
        print(f"    [{mark}]  {row['label']}")
    print("-" * 64)
    print("  WHAT TO DO IN PLAIN ENGLISH")
    if plan["action"] in ("BUY NOW", "BUY BREAKOUT"):
        print("    1) Enter near the price above")
        print("    2) Place the stop immediately")
        print("    3) Let winners run with the trail; cut losers at the stop")
    elif plan["action"].startswith("AVOID"):
        print("    1) Skip this name — structure/volume says no")
        print("    2) Re-run later or pick from `rotate` / `picks`")
    elif plan["action"] == "BREAKOUT WATCH":
        print(f"    1) {plan['do_next']}")
        print("    2) Volume must expand on the break — quiet drift through = ignore")
        print("    3) Re-run once the alert fires")
    elif plan["action"] == "PULLBACK ZONE":
        print(f"    1) {plan['do_next']}")
        print("    2) Best dips tag the 22 EMA with quiet volume, then resume with volume")
    else:
        print(f"    1) {plan['do_next']}")
        print("    2) Re-run this command after the alert/condition hits")
        print("    3) Or run:  .venv/bin/python3 tools/trade_desk.py rotate --top 5")
    ranks = payload.get("model_ranks_for_symbol") or []
    if ranks:
        print("-" * 64)
        print("  BEST MODELS FOR THIS STOCK (past backtests)")
        for r in ranks[:3]:
            print(
                f"    #{r['rank']} {r['model']:<20} "
                f"won {r['win_rate']:.0%} of trades, Sharpe {r['sharpe']:.2f}"
            )
        print("    Tip: retry with  --model auto  to use #1 engine for this name")
    print("=" * 64)
    print()


def _print_rank(rows: list[dict], title: str) -> None:
    print()
    print("=" * 78)
    print(f"  {title}")
    print("=" * 78)
    print(f"  {'#':<3} {'model':<22} {'score':>6} {'WR':>6} {'Sh':>6} {'PF':>6} {'DD':>7} {'ret':>7}")
    for r in rows[:15]:
        print(
            f"  {r['rank']:<3} {r['model']:<22} {r['score']:>6.3f} "
            f"{r['win_rate']:>5.0%} {r['sharpe']:>6.2f} {r['profit_factor']:>6.2f} "
            f"{r['max_drawdown']:>7.1%} {r['total_return']:>7.1%}"
        )
    print("-" * 78)
    print(f"  Default: {DEFAULT_MODEL}   Engines: {', '.join(list_engine_models())}")
    print("=" * 78)
    print()


def _print_picks(rows: list[dict], horizon: str) -> None:
    print()
    print("=" * 72)
    print(f"  SECTOR LEADERS — {horizon.upper()}  ({len(rows)} names scanned)")
    print("=" * 72)
    playable = [r for r in rows if r.get("setup_kind") in ("classic_buy", "breakout_buy") or r.get("setup_ok")]
    breakouts = [r for r in rows if r.get("setup_kind") == "breakout_watch" or r.get("action") == "BREAKOUT WATCH"]
    pullbacks = [r for r in rows if r.get("setup_kind") == "pullback_watch" or r.get("action") == "PULLBACK ZONE"]
    almost = [
        r for r in rows
        if not r.get("setup_ok") and "error" not in r
        and r.get("confidence", 0) >= 0.65
        and r.get("action") in ("WAIT", "WAIT (almost ready)")
    ]
    avoid = [r for r in rows if str(r.get("action", "")).startswith("AVOID")]

    print("\n  BUY NOW / BUY BREAKOUT")
    if not playable:
        print("    None live — use BREAKOUT WATCH + PULLBACK ZONE.")
    for r in playable[:12]:
        tag = "BREAKOUT" if r.get("setup_kind") == "breakout_buy" else "CLASSIC"
        rv = r.get("rvol")
        rv_s = f" rvol {rv:.1f}x" if rv is not None else ""
        print(
            f"    [{tag}] {r['symbol']:<5} [{r.get('sector','?'):<9}]  "
            f"~${r['price']:.2f}{rv_s}  stop ${r['stop']:.2f}  "
            f"risk ${r['dollar_risk']:.0f}  conf {r['confidence']:.0%}"
        )

    print("\n  ABOUT TO BREAK OUT (volume waking — wait for SURGE)")
    if not breakouts:
        print("    (none)")
    for r in breakouts[:15]:
        lvl = r.get("breakout_level")
        rv = r.get("rvol")
        tip = f"buy-stop > ${lvl:.2f}" if lvl else (r.get("do_next") or "")[:80]
        rv_s = f" rvol {rv:.1f}x" if rv is not None else ""
        print(
            f"    {r['symbol']:<5} [{r.get('sector','?'):<9}]  "
            f"${r['price']:.2f}{rv_s}  conf {r['confidence']:.0%}  → {tip}"
        )

    print("\n  PULLBACK ZONE (wait for dip into value)")
    if not pullbacks:
        print("    (none)")
    for r in pullbacks[:12]:
        tip = (r.get("do_next") or "")[:85]
        print(f"    {r['symbol']:<5} [{r.get('sector','?'):<9}]  ${r['price']:.2f}  → {tip}")

    print("\n  OTHER HIGH-CONF WAIT")
    by_sec: dict[str, list] = {}
    for r in almost:
        by_sec.setdefault(r.get("sector", "other"), []).append(r)
    shown = 0
    for sec in [
        "memory", "photonics", "energy", "space", "quantum", "mag7",
        "ai_infra", "banks", "biotech", "metals", "consumer", "crypto", "beta", "other",
    ]:
        bucket = by_sec.get(sec) or []
        if not bucket:
            continue
        print(f"    — {sec} —")
        for r in bucket[:3]:
            tip = (r.get("do_next") or "")[:90]
            print(
                f"      {r['symbol']:<5} ${r['price']:.2f}  conf {r['confidence']:.0%}  "
                f"→ {tip}"
            )
            shown += 1
        if shown >= 18:
            break
    if shown == 0:
        print("    (none)")

    if avoid:
        print("\n  AVOID right now")
        for r in avoid[:8]:
            print(f"    {r['symbol']:<5} [{r.get('sector','?'):<9}]  {r.get('do_next','')[:80]}")

    print("\n  How to use")
    print("    • BUY NOW / BUY BREAKOUT = trade (breakout requires volume surge)")
    print("    • BREAKOUT WATCH = near highs — only take volume-led breaks")
    print("    • PULLBACK ZONE = prefer 22 EMA / value dips")
    print("    • Lost 200 EMA = structural break → skip (live advisory)")
    print("    • Per-stock engines:  --model auto   (see PERF_MODEL_ROUTING.md)")
    print("    • Drill in:  .venv/bin/python3 tools/trade_desk.py TICKER --model auto")
    print("=" * 72)
    print()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="POC/VA trade desk (multi-model)")
    p.add_argument(
        "command",
        nargs="?",
        help="Symbol, 'picks', 'rotate', 'rank', 'risk', 'watch', or 'openscan'",
    )
    p.add_argument(
        "rest",
        nargs="*",
        help="For watch: tickers, comma-list, or 'rotate'. For risk: symbol.",
    )
    p.add_argument("--account", type=float, default=100_000, help="Account equity (default 100000)")
    p.add_argument("--risk-pct", type=float, default=0.01, help="Max risk fraction per trade (default 1%%)")
    p.add_argument("--horizon", choices=["day", "week"], default="day", help="For picks/rotate: day or week")
    p.add_argument("--top", type=int, default=5, help="For rotate/openscan: top N sectors or plays")
    p.add_argument("--deep", type=int, default=24, help="For openscan: VPA candidates to deep-analyze")
    p.add_argument("--fast", action="store_true", help="For openscan: VPA screen only")
    p.add_argument("--full", action="store_true", help="For openscan: full DEFAULT_WATCH universe")
    p.add_argument("--symbols", type=str, default="", help="Comma watchlist for picks/watch")
    p.add_argument(
        "--sectors",
        type=str,
        default="",
        help="Comma sectors for picks: mag7,memory,photonics,energy,space,quantum,ai_infra,banks,biotech,metals,consumer,crypto,beta",
    )
    p.add_argument(
        "--model",
        type=str,
        default=equity_default_model(),
        help=f"Model engine ({'/'.join(list_engine_models()[:8])}…) or 'auto' (default=WINNER)",
    )
    p.add_argument("--symbol", type=str, default="", help="For rank: rank models on this symbol")
    p.add_argument("--engines-only", action="store_true", help="For rank: only runnable engines")
    p.add_argument("--json", action="store_true", help="Print raw JSON")
    p.add_argument("--period", type=str, default="60d", help="yfinance lookback period")
    p.add_argument("--every", type=int, default=30, help="For watch: refresh seconds (min 15)")
    p.add_argument(
        "--interval",
        type=str,
        default="5m",
        help="For watch: bar size (5m default; use 1m near open for faster tape)",
    )
    p.add_argument("--no-clear", action="store_true", help="For watch: don't clear screen each tick")
    p.add_argument("--ticks", type=int, default=0, help="For watch: stop after N ticks (0=forever)")
    # v25 risk plan knobs
    p.add_argument("--conf", type=float, default=None, help="For risk: model confidence 0-1 (else from engine)")
    p.add_argument("--vol-z", type=float, default=0.0, help="For risk: 20d volume z-score")
    p.add_argument("--peak", type=float, default=0.0, help="For risk: equity high-water mark")
    p.add_argument("--qqq-ok", action="store_true", help="For risk: QQQ trend ok")
    p.add_argument("--defensive", action="store_true", help="For risk: XLP/SPY defensive on")
    p.add_argument("--no-options", action="store_true", help="For risk: options unaffordable")
    p.add_argument("--history", type=str, default="", help="For risk: recent closed PnL list e.g. 1,-1,0.2")
    args = p.parse_args(argv)

    if not args.command:
        p.print_help()
        print("\nExamples:")
        print("  python3 tools/trade_desk.py TSLA --account 50000")
        print("  python3 tools/trade_desk.py MU --model auto")
        print("  python3 tools/trade_desk.py rank")
        print("  python3 tools/trade_desk.py rank --symbol IONQ")
        print("  python3 tools/trade_desk.py rotate")
        print("  python3 tools/trade_desk.py rotate --top 5 --horizon day")
        print("  python3 tools/trade_desk.py picks --horizon week --model v14_risk_kelly")
        print("  python3 tools/trade_desk.py risk APLD --account 1000 --conf 0.85 --vol-z 1.8 --qqq-ok")
        print("  python3 tools/trade_desk.py watch NVDA --every 30")
        print("  python3 tools/trade_desk.py watch NVDA,MU,ANET --every 45 --interval 5m")
        print("  python3 tools/trade_desk.py watch rotate --every 90 --top 3")
        print("  python3 tools/trade_desk.py openscan              # full-market open plays")
        print("  python3 tools/trade_desk.py openscan --top 12 --json")
        print("  python3 tools/trade_desk.py watch --symbols NVDA,IBIT,ANET --interval 1m --every 20")
        return 0

    cmd = args.command.strip().lower()
    if cmd == "risk":
        sym = (args.rest[0] if args.rest else args.symbol or "").strip().upper()
        if not sym:
            raise SystemExit("risk: pass a symbol, e.g. trade_desk.py risk APLD --account 1000")
        conf = args.conf
        if conf is None:
            try:
                payload = analyze(sym, args.account, args.risk_pct, period=args.period, model=args.model)
                conf = float(payload.get("confidence") or payload.get("conf") or 0.65)
            except Exception:  # noqa: BLE001
                conf = 0.65
        hist: list[float] = []
        if args.history.strip():
            hist = [float(x) for x in args.history.split(",") if x.strip()]
        peak = args.peak if args.peak > 0 else args.account
        setup = SetupSnapshot(
            symbol=sym,
            model_conf=float(conf),
            vol_z=float(args.vol_z),
            trend_ok=True,
            macro_ok=not args.defensive,
            qqq_ok=True if not hasattr(args, "qqq_ok") else (bool(args.qqq_ok) if args.qqq_ok else True),
            options_affordable=not args.no_options,
        )
        state = PortfolioState(equity=float(args.account), peak=float(peak), trade_pnl_history=hist)
        dec = plan_entry(setup, state)
        d = decision_to_dict(dec)
        d["symbol"] = sym
        d["account"] = args.account
        d["model_conf_used"] = conf
        if args.json:
            print(_safe_json(d, indent=2))
        else:
            print(f"=== RISK  {sym}  ${args.account:,.0f}  conf={conf:.2f} ===")
            print(f"MODE {dec.mode}  VEHICLE {dec.vehicle}  ACTION {dec.action}")
            print(f"RISK {dec.risk_pct:.1%} → max loss ${dec.max_loss_dollars:,.0f}  size×{dec.size_mult:.2f}")
            for r in dec.reasons:
                print(f"  • {r}")
            print("EXIT RULES")
            for k, v in dec.exit_rules.items():
                print(f"  {k}: {v}")
            if dec.mode == "OPTIONS_ATTACK":
                print(f"\n→ options_picker.py --symbol {sym} --account {args.account:.0f} --risk-pct {dec.risk_pct:.2f}")
            elif dec.mode == "EQUITY_HEDGE":
                print(f"\n→ trade_desk.py {sym} --model v25_regime_grow --account {args.account:.0f}")
            print("\nPlaybook: models/poc_va_macdha/v25_regime_grow/RISK_PLAYBOOK.md")
        return 0

    if cmd == "rank":
        if args.symbol:
            rows = rank_models_for_symbol(args.symbol, engines_only=args.engines_only)
            title = f"MODEL RANK ON {args.symbol.upper()}  (hist backtest)"
        else:
            rows = rank_models(engines_only=args.engines_only)
            title = "OVERALL MODEL RANK  (portfolio hist)"
        if args.json:
            print(_safe_json(rows, indent=2))
        else:
            _print_rank(rows, title)
        return 0

    if cmd in ("openscan", "open-scan", "open_scan", "scanner"):
        from open_scan import run_open_scan, _print_human

        payload = run_open_scan(
            account=float(args.account),
            risk_pct=float(args.risk_pct),
            model=str(args.model or "auto"),
            universe="full" if getattr(args, "full", False) else "open",
            top=max(1, int(args.top or 12)),
            deep_n=max(8, int(getattr(args, "deep", 0) or 24)),
            fast_only=bool(getattr(args, "fast", False)),
            quiet=args.json,
        )
        if args.json:
            print(_safe_json(payload, indent=2))
        else:
            _print_human(payload)
        return 0 if payload.get("ok") else 1

    if cmd == "watch":
        # Resolve symbol list
        bits: list[str] = []
        if args.symbols.strip():
            bits.extend(s.strip() for s in args.symbols.split(",") if s.strip())
        for tok in args.rest:
            bits.extend(s.strip() for s in tok.split(",") if s.strip())
        use_rotate = any(b.lower() == "rotate" for b in bits) or (not bits)
        symbols: list[str] = []
        if use_rotate and (not bits or bits == ["rotate"] or "rotate" in [b.lower() for b in bits]):
            print("Resolving hot sectors for live board…", flush=True)
            flows = rank_sector_flows()
            top = [r for r in flows if "error" not in r][: max(1, args.top)]
            for sec in top:
                symbols.extend((sec.get("members") or [])[:6])  # cap per sector for speed
            # drop rotate token from bits if mixed
            extra = [b for b in bits if b.lower() != "rotate"]
            symbols.extend(extra)
            print(f"Hot sectors: {', '.join(t['sector'] for t in top)}", flush=True)
        else:
            symbols = bits
        # unique preserve order
        seen: set[str] = set()
        symbols = [s.upper() for s in symbols if not (s.upper() in seen or seen.add(s.upper()))]
        if not symbols:
            raise SystemExit("watch: pass tickers, --symbols, or 'rotate'")
        # keep board readable
        if len(symbols) > 18:
            symbols = symbols[:18]
            print(f"Watching first 18 names for speed: {', '.join(symbols)}", flush=True)
        return run_watch(
            symbols,
            args.account,
            args.risk_pct,
            args.model,
            every=args.every,
            interval=args.interval,
            clear=not args.no_clear,
            max_ticks=(args.ticks or None),
        )

    if cmd == "rotate":
        payload = rotate_picks(
            args.account, args.risk_pct, args.horizon, args.model, top_n=max(1, args.top)
        )
        if args.json:
            print(_safe_json(payload, indent=2))
        else:
            _print_rotate(payload, args.horizon)
        return 0

    if cmd == "picks":
        if args.symbols.strip():
            symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
        elif args.sectors.strip():
            symbols = []
            for sec in args.sectors.split(","):
                sec = sec.strip().lower()
                if sec not in SECTORS:
                    raise SystemExit(f"Unknown sector '{sec}'. Choose: {', '.join(SECTORS)}")
                symbols.extend(SECTORS[sec])
            # unique
            seen = set()
            symbols = [s for s in symbols if not (s in seen or seen.add(s))]
        else:
            symbols = list(DEFAULT_WATCH)
        print(f"Scanning {len(symbols)} names…", flush=True)
        rows = scan_picks(symbols, args.account, args.risk_pct, args.horizon, model=args.model)
        if args.json:
            print(_safe_json({"horizon": args.horizon, "model": args.model, "picks": rows}, indent=2))
        else:
            _print_picks(rows, args.horizon)
        return 0

    payload = analyze(args.command, args.account, args.risk_pct, period=args.period, model=args.model)
    if args.json:
        print(_safe_json(payload, indent=2))
    else:
        _print_analyze(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
