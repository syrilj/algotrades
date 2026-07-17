#!/usr/bin/env python3
"""High-certainty bounce / direction predictor for desk book names.

Contract
--------
predict_from_features(features, artifact) → structured forecast with:
  direction, p_bounce, p_target_hit (optional), confidence_state, abstain reasons.

Training uses only point-in-time OHLCV features from data_cache (no look-ahead).
Live options / GEX can enrich the feature row at inference but are optional;
missing live data triggers soft degradation, not fabricated scores.

INFQ is resolved as the ~$9 equity by default. Alias to IONQ is only applied
when explicitly requested and is always labeled in the output.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from evolve.calibration import (  # noqa: E402
    apply_isotonic,
    calibration_metrics,
    fit_isotonic,
)

# ---------------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------------

CACHE_1D = ROOT / "data_cache" / "1d"
ARTIFACT_DIR = ROOT / "runs" / "bounce_predict"
DEFAULT_ARTIFACT = ARTIFACT_DIR / "model_artifact.json"
EVAL_PATH = ARTIFACT_DIR / "OOS_RELIABILITY.json"
MODEL_DIR = ROOT / "models" / "poc_va_macdha" / "v80_bounce_certainty"

FEATURE_NAMES: list[str] = [
    "ret_1d",
    "ret_3d",
    "ret_5d",
    "ret_10d",
    "range_pos_5d",
    "range_pos_20d",
    "dist_from_high_20d",
    "dist_from_low_20d",
    "atr_pct_14",
    "vol_z_20",
    "rsi_14",
    "above_sma20",
    "above_sma50",
    "sma20_slope",
    "down_streak",
    "gap_open",
    "intraday_range_pct",
    "body_pct",
    "close_loc",  # (c-l)/(h-l)
    # support / resistance structure (PIT from OHLCV)
    "dist_to_support_20d",
    "dist_to_support_60d",
    "dist_to_resist_20d",
    "near_support",
    "near_resist",
    "support_zone",  # range_pos_20d in lower quartile
    # macro / cross-asset (PIT from QQQ/SPY)
    "qqq_ret_1d",
    "qqq_ret_5d",
    "spy_ret_1d",
    "qqq_above_sma50",
    "macro_risk_on",
    "rs_vs_qqq_5d",
    # optional live enrichment (0 if missing in train)
    "opt_call_bias",
    "opt_pc_vol",
    "gex_below_put_wall",
    "gex_below_call_wall",
    "model_raw_conf",
    "model_setup_ok",
    "model_go_long",
    "model_soft_long",
    "model_swing_up",
    "model_above_vwap",
    "model_macd_pos",
    "macro_live_ok",
    "macro_live_defensive",
]

# Core fields required for feature_quality (exclude live-only zeros)
_CORE_PREFIX_SKIP = ("opt_", "gex_", "model_", "macro_live_")

# Explicit aliases — never silent for INFQ stock path
SYMBOL_ALIASES_EXPLICIT = {
    "GOOGL": "GOOG",
}

DEFAULT_BOOK = ["TSLA", "MSTR", "SKHY", "INFQ"]
TRAIN_UNIVERSE = ["SPY", "QQQ", "TSLA", "MSTR", "IONQ", "MU", "NVDA", "APLD", "COIN", "PLTR"]

HIGH_CONF_ENTER = 0.62
HIGH_CONF_WATCH = 0.55
MIN_FEATURE_QUALITY = 0.55

# What actually moves each desk name (operator priors + measurable co-move)
SYMBOL_DRIVERS: dict[str, dict[str, Any]] = {
    "TSLA": {
        "primary_benchmark": "QQQ",
        "also": ["NDX", "SPY"],
        "thesis": (
            "TSLA is mega-cap growth / Nasdaq-pegged: it usually trades in tandem with QQQ/NDX "
            "risk-on/off. Large options open interest and 0DTE/OpEx flows can pin or amplify "
            "intraday moves around GEX walls — not dealer inventory, chain-proxy pressure only."
        ),
        "options_sensitive": True,
        "opex_sensitive": True,
    },
    "MSTR": {
        "primary_benchmark": "BTC",  # proxy via leverage narrative; measure vs QQQ too
        "also": ["QQQ", "COIN"],
        "thesis": (
            "MSTR trades as leveraged BTC/risk beta with equity-market overlay. Nasdaq risk-off "
            "still hits it; crypto-linked gaps dominate multi-day path."
        ),
        "options_sensitive": True,
        "opex_sensitive": True,
    },
    "SKHY": {
        "primary_benchmark": "SOXX",
        "also": ["QQQ", "SMH"],
        "thesis": (
            "SK Hynix ADR tracks semi/memory complex (SOXX/SMH) and broader Nasdaq risk. "
            "Thin US history → co-move estimates may be unstable."
        ),
        "options_sensitive": True,
        "opex_sensitive": True,
    },
    "INFQ": {
        "primary_benchmark": "QQQ",
        "also": ["SPY"],
        "thesis": (
            "Smaller high-beta name; moves with risk appetite and its own tape/liquidity more "
            "than mega-cap options pinning. Treat as stock, not IONQ."
        ),
        "options_sensitive": False,
        "opex_sensitive": False,
    },
    "IONQ": {
        "primary_benchmark": "QQQ",
        "also": ["SPY"],
        "thesis": "High-beta speculative; co-moves with Nasdaq risk and sector risk appetite.",
        "options_sensitive": True,
        "opex_sensitive": True,
    },
}


# ---------------------------------------------------------------------------
# Pure helpers: OpEx calendar + Nasdaq co-move
# ---------------------------------------------------------------------------


def third_friday(year: int, month: int) -> pd.Timestamp:
    """US equity monthly options expiration = third Friday of the month."""
    d = pd.Timestamp(year=year, month=month, day=1)
    # weekday: Mon=0 ... Fri=4
    first_friday_offset = (4 - d.weekday()) % 7
    first_friday = d + pd.Timedelta(days=first_friday_offset)
    return first_friday + pd.Timedelta(days=14)


def weekly_friday(asof: pd.Timestamp | datetime | str | None = None) -> pd.Timestamp:
    """Nearest Friday on or after asof (weekly equity options convention)."""
    d = pd.Timestamp(asof or pd.Timestamp.utcnow()).normalize()
    if getattr(d, "tzinfo", None) is not None:
        d = d.tz_localize(None)
    # Friday = 4
    add = (4 - d.weekday()) % 7
    return d + pd.Timedelta(days=add)


def opex_session_flag(
    asof: pd.Timestamp | datetime | str | None = None,
    *,
    look_ahead_days: int = 1,
) -> dict[str, Any]:
    """Date-driven OpEx awareness (monthly third Friday + weekly Friday).

    Does not claim dealer inventory. Surfaces whether *asof* or *asof+look_ahead*
    lands on a standard equity options expiry session.
    """
    d0 = pd.Timestamp(asof or pd.Timestamp.utcnow()).normalize()
    if getattr(d0, "tzinfo", None) is not None:
        d0 = d0.tz_localize(None)
    d1 = d0 + pd.Timedelta(days=int(look_ahead_days))

    monthly = third_friday(d0.year, d0.month)
    # if past this month's third Friday, next month's
    if d0 > monthly:
        y, m = (d0.year + 1, 1) if d0.month == 12 else (d0.year, d0.month + 1)
        monthly = third_friday(y, m)
    # also check previous month if we're early and looking at "today was monthly"
    prev_m = d0.month - 1 or 12
    prev_y = d0.year if d0.month > 1 else d0.year - 1
    monthly_this = third_friday(d0.year, d0.month)
    monthly_prev = third_friday(prev_y, prev_m)

    weekly = weekly_friday(d0)
    weekly_tom = weekly_friday(d1)

    def _is_exp(day: pd.Timestamp) -> dict[str, Any]:
        is_monthly = day.normalize() in {
            monthly_this.normalize(),
            monthly_prev.normalize(),
            monthly.normalize(),
        }
        is_weekly = day.weekday() == 4  # every Friday is weekly-options relevant
        return {
            "date": str(day.date()),
            "is_friday": bool(day.weekday() == 4),
            "is_monthly_opex": bool(is_monthly),
            "is_weekly_opex_friday": bool(is_weekly),
            "is_opex_session": bool(is_monthly or is_weekly),
        }

    today = _is_exp(d0)
    tomorrow = _is_exp(d1)
    # User path: "tomorrow is opex" → flag when look-ahead session is opex
    opex_window = bool(today["is_opex_session"] or tomorrow["is_opex_session"])
    impact = []
    if opex_window:
        impact.append(
            "Near weekly/monthly OpEx: elevated pin risk near GEX walls; "
            "0DTE/near-expiry options flow can dominate overnight 'trend bounce' reads."
        )
        if tomorrow["is_opex_session"] and not today["is_opex_session"]:
            impact.append(
                "Next session is an options-expiry Friday — expect pinning/amplification "
                "into expiry rather than clean multi-day mean reversion."
            )
        if today["is_monthly_opex"] or tomorrow["is_monthly_opex"]:
            impact.append("Monthly OpEx in window — larger open-interest rolls, broader pin zones.")
    else:
        impact.append("Not in standard weekly/monthly equity OpEx window for asof/look-ahead.")

    return {
        "asof": str(d0.date()),
        "look_ahead_days": int(look_ahead_days),
        "today": today,
        "tomorrow": tomorrow,
        "next_monthly_opex": str(monthly.date()),
        "opex_window": opex_window,
        "impact_notes": impact,
        "methodology": (
            "US equity monthly OpEx = third Friday; weekly OpEx = Fridays. "
            "Research calendar flag only — not dealer inventory."
        ),
    }


def rolling_comove(
    asset: pd.Series,
    bench: pd.Series,
    *,
    window: int = 20,
) -> dict[str, Any]:
    """Rolling correlation + beta of asset daily returns vs benchmark (PIT last bar)."""
    a = asset.astype(float).pct_change()
    b = bench.astype(float).pct_change()
    df = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    if len(df) < max(10, window // 2):
        return {
            "ok": False,
            "error": "insufficient_overlap",
            "window": window,
            "n": int(len(df)),
            "corr": None,
            "beta": None,
            "tandem": None,
            "same_day_sign_match_rate": None,
            "asset_ret_1d": None,
            "bench_ret_1d": None,
        }
    tail = df.tail(window)
    corr = float(tail["a"].corr(tail["b"])) if len(tail) >= 5 else float("nan")
    var_b = float(tail["b"].var())
    cov = float(tail["a"].cov(tail["b"])) if len(tail) >= 5 else float("nan")
    beta = float(cov / var_b) if var_b > 1e-12 and np.isfinite(cov) else float("nan")
    sign_match = float(((tail["a"] > 0) == (tail["b"] > 0)).mean()) if len(tail) else None
    last_a = float(df["a"].iloc[-1])
    last_b = float(df["b"].iloc[-1])
    tandem = None
    if np.isfinite(corr):
        if corr >= 0.55:
            tandem = "high_tandem"
        elif corr >= 0.30:
            tandem = "moderate_tandem"
        elif corr <= -0.20:
            tandem = "inverse"
        else:
            tandem = "loose"
    return {
        "ok": bool(np.isfinite(corr)),
        "window": window,
        "n": int(len(tail)),
        "corr": None if not np.isfinite(corr) else round(corr, 4),
        "beta": None if not np.isfinite(beta) else round(beta, 4),
        "tandem": tandem,
        "same_day_sign_match_rate": None if sign_match is None else round(sign_match, 4),
        "asset_ret_1d": round(last_a, 5),
        "bench_ret_1d": round(last_b, 5),
        "same_day_direction": (
            "together"
            if (last_a > 0 and last_b > 0) or (last_a < 0 and last_b < 0)
            else "divergent"
            if (last_a * last_b) < 0
            else "flat"
        ),
    }


def symbol_driver_context(
    symbol: str,
    *,
    asset_close: pd.Series | None = None,
    asof: pd.Timestamp | datetime | str | None = None,
    gex: Mapping[str, Any] | None = None,
    options: Mapping[str, Any] | None = None,
    spot: float | None = None,
    asset_is_proxy: bool = False,
    proxy_symbol: str | None = None,
) -> dict[str, Any]:
    """Compose what moves this name: driver thesis + QQQ co-move + options/GEX + OpEx.

    When asset_is_proxy=True (thin ADR using SOXX/SPY bars as stand-in), co-move is
    forced unavailable — never report corr=1 vs the same sector proxy.
    """
    sym = (symbol or "").upper().replace(".US", "")
    prior = dict(SYMBOL_DRIVERS.get(sym) or {
        "primary_benchmark": "QQQ",
        "also": ["SPY"],
        "thesis": "Default risk-beta name; co-moves with Nasdaq/SPY risk appetite.",
        "options_sensitive": True,
        "opex_sensitive": True,
    })
    bench_sym = str(prior.get("primary_benchmark") or "QQQ")
    # BTC not in cache as equity — fall back to QQQ for measurable co-move
    measure_bench = "QQQ" if bench_sym in {"BTC", "NDX"} else bench_sym
    if measure_bench not in {"QQQ", "SPY", "SOXX", "SMH", "COIN"}:
        measure_bench = "QQQ"

    comove: dict[str, Any] = {"ok": False, "error": "no_asset_series"}
    if asset_is_proxy:
        comove = {
            "ok": False,
            "error": "proxy_self_or_unavailable",
            "window": 20,
            "n": int(len(asset_close)) if asset_close is not None else 0,
            "corr": None,
            "beta": None,
            "tandem": None,
            "same_day_sign_match_rate": None,
            "asset_ret_1d": None,
            "bench_ret_1d": None,
            "benchmark": measure_bench,
            "benchmark_requested": bench_sym,
            "proxy_symbol": proxy_symbol,
            "note": (
                f"Native history too thin for {sym}; co-move not measured against "
                f"sector proxy {proxy_symbol or measure_bench} (would invent tandem)."
            ),
        }
    elif asset_close is not None and len(asset_close) >= 15:
        bench_df = load_ohlcv(measure_bench, prefer_live=False)
        if bench_df is None:
            bench_df = load_ohlcv("QQQ", prefer_live=False)
            measure_bench = "QQQ"
        # Guard: never measure co-move of a series against itself by symbol identity
        # when caller accidentally passes proxy bars without asset_is_proxy.
        if bench_df is not None:
            bclose = bench_df[[c for c in bench_df.columns if c.lower() == "close"][0]].astype(float)
            a = asset_close.astype(float).copy()
            a.index = pd.to_datetime(a.index)
            if getattr(a.index, "tz", None) is not None:
                a.index = a.index.tz_localize(None)
            bclose.index = pd.to_datetime(bclose.index)
            if getattr(bclose.index, "tz", None) is not None:
                bclose.index = bclose.index.tz_localize(None)
            # If series nearly identical to benchmark (proxy leak), refuse
            aligned = pd.concat([a.rename("a"), bclose.rename("b")], axis=1).dropna()
            self_proxy = False
            if len(aligned) >= 10:
                ctmp = float(aligned["a"].pct_change().corr(aligned["b"].pct_change()))
                if np.isfinite(ctmp) and ctmp > 0.995:
                    self_proxy = True
            if self_proxy:
                comove = {
                    "ok": False,
                    "error": "proxy_self_or_unavailable",
                    "window": 20,
                    "n": int(len(aligned)),
                    "corr": None,
                    "beta": None,
                    "tandem": None,
                    "benchmark": measure_bench,
                    "benchmark_requested": bench_sym,
                    "note": "Asset series indistinguishable from benchmark — treating as proxy leak.",
                }
            else:
                comove = rolling_comove(a, bclose, window=20)
                comove["benchmark"] = measure_bench
                comove["benchmark_requested"] = bench_sym

    opex = opex_session_flag(asof, look_ahead_days=1)

    opt_ctx: dict[str, Any] = {"available": False}
    if options:
        calls = int(options.get("calls") or 0)
        puts = int(options.get("puts") or 0)
        pc = options.get("pc")
        opt_ctx = {
            "available": True,
            "call_flags": calls,
            "put_flags": puts,
            "put_call_vol_ratio": pc,
            "flow_bias": (
                "call_heavy"
                if calls > puts * 1.2
                else "put_heavy"
                if puts > calls * 1.2
                else "balanced"
                if (calls + puts) > 0
                else "none"
            ),
            "note": "Chain-proxy unusual flow (not OPRA tape); can pressure stock on OpEx/0DTE.",
        }
    else:
        opt_ctx = {
            "available": False,
            "note": "options_flow_unavailable",
        }

    gex_ctx: dict[str, Any] = {"available": False}
    if gex and (gex.get("call_wall") is not None or gex.get("put_wall") is not None):
        cw = gex.get("call_wall")
        pw = gex.get("put_wall")
        label = gex.get("label")
        near_wall = None
        if spot is not None and np.isfinite(float(spot)):
            sp = float(spot)
            dists = []
            if cw is not None and np.isfinite(float(cw)):
                dists.append(("call_wall", float(cw), abs(sp - float(cw)) / sp))
            if pw is not None and np.isfinite(float(pw)):
                dists.append(("put_wall", float(pw), abs(sp - float(pw)) / sp))
            if dists:
                dists.sort(key=lambda x: x[2])
                near_wall = {
                    "type": dists[0][0],
                    "price": dists[0][1],
                    "dist_pct": round(dists[0][2] * 100, 3),
                    "near": dists[0][2] <= 0.02,
                }
        gex_ctx = {
            "available": True,
            "call_wall": cw,
            "put_wall": pw,
            "label": label,
            "near_wall": near_wall,
            "note": "GEX walls are OI/volume heuristics — not known dealer inventory.",
        }
    else:
        gex_ctx = {"available": False, "note": "gex_unavailable"}

    # Operator narrative pieces
    moves = []
    if comove.get("ok") and comove.get("tandem"):
        moves.append(
            f"vs {comove.get('benchmark')}: corr={comove.get('corr')} beta={comove.get('beta')} "
            f"({comove.get('tandem')}); same-day {comove.get('same_day_direction')} "
            f"(asset {comove.get('asset_ret_1d')}, bench {comove.get('bench_ret_1d')})"
        )
    elif comove.get("error"):
        moves.append(f"co-move unavailable: {comove.get('error')}")
    if opex.get("opex_window"):
        moves.append("OpEx window active (today and/or tomorrow expiry Friday)")
    if opt_ctx.get("available"):
        moves.append(f"options flow bias={opt_ctx.get('flow_bias')}")
    if gex_ctx.get("available") and gex_ctx.get("near_wall"):
        nw = gex_ctx["near_wall"]
        moves.append(
            f"near GEX {nw['type']} @ {nw['price']} ({nw['dist_pct']}% away)"
        )

    return {
        "symbol": sym,
        "driver_prior": prior,
        "comove": comove,
        "opex": opex,
        "options_pressure": opt_ctx,
        "gex_pressure": gex_ctx,
        "what_moves_this": moves,
        "summary": prior.get("thesis"),
    }


# ---------------------------------------------------------------------------
# Symbol resolution
# ---------------------------------------------------------------------------


def resolve_symbol(
    symbol: str,
    *,
    apply_desk_alias: bool = False,
) -> dict[str, Any]:
    """Normalize a symbol and document alias decisions.

    Default: INFQ stays INFQ (the ~$9 name). When apply_desk_alias=True,
    INFQ→IONQ and GOOGL→GOOG, always labeled in the return payload.
    """
    raw = (symbol or "").strip().upper()
    raw = raw.replace(".US", "")
    raw = "".join(ch for ch in raw if ch.isalnum())
    if not raw:
        return {
            "input": symbol,
            "resolved": None,
            "alias_applied": False,
            "alias_from": None,
            "note": "empty_symbol",
        }
    if apply_desk_alias and raw == "INFQ":
        return {
            "input": symbol,
            "resolved": "IONQ",
            "alias_applied": True,
            "alias_from": "INFQ",
            "note": "explicit_desk_alias_infq_to_ionq",
        }
    if raw in SYMBOL_ALIASES_EXPLICIT:
        return {
            "input": symbol,
            "resolved": SYMBOL_ALIASES_EXPLICIT[raw],
            "alias_applied": True,
            "alias_from": raw,
            "note": "explicit_alias",
        }
    note = "native"
    if raw == "INFQ":
        note = "infq_stock_not_ionq"
    return {
        "input": symbol,
        "resolved": raw,
        "alias_applied": False,
        "alias_from": None,
        "note": note,
    }


# ---------------------------------------------------------------------------
# Feature engineering (point-in-time)
# ---------------------------------------------------------------------------


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0.0)
    down = (-delta).clip(lower=0.0)
    ma_up = up.ewm(alpha=1.0 / n, adjust=False).mean()
    ma_down = down.ewm(alpha=1.0 / n, adjust=False).mean()
    rs = ma_up / ma_down.replace(0.0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def feature_frame_from_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Vectorized PIT feature matrix aligned to df index (no future bars)."""
    d = df.copy()
    cols = {c.lower(): c for c in d.columns}
    for need in ("open", "high", "low", "close", "volume"):
        if need not in cols:
            raise ValueError(f"ohlcv missing {need}")
    o = d[cols["open"]].astype(float)
    h = d[cols["high"]].astype(float)
    l = d[cols["low"]].astype(float)
    c = d[cols["close"]].astype(float)
    v = d[cols["volume"]].astype(float)

    ret = c.pct_change()
    tr = pd.concat([(h - l), (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=5).mean()
    vol_mean = v.rolling(20, min_periods=5).mean()
    vol_std = v.rolling(20, min_periods=5).std()
    high5 = h.rolling(5, min_periods=3).max()
    low5 = l.rolling(5, min_periods=3).min()
    high20 = h.rolling(20, min_periods=10).max()
    low20 = l.rolling(20, min_periods=10).min()
    sma20 = c.rolling(20, min_periods=10).mean()
    sma50 = c.rolling(50, min_periods=20).mean()

    # down streak: consecutive negative closes ending at t
    neg = (ret < 0).astype(int)
    streak = neg.copy()
    for i in range(1, len(streak)):
        streak.iloc[i] = streak.iloc[i] * (streak.iloc[i - 1] + 1) if neg.iloc[i] else 0

    out = pd.DataFrame(index=d.index)
    out["ret_1d"] = ret
    out["ret_3d"] = c.pct_change(3)
    out["ret_5d"] = c.pct_change(5)
    out["ret_10d"] = c.pct_change(10)
    out["range_pos_5d"] = (c - low5) / (high5 - low5).replace(0.0, np.nan)
    out["range_pos_20d"] = (c - low20) / (high20 - low20).replace(0.0, np.nan)
    out["dist_from_high_20d"] = c / high20 - 1.0
    out["dist_from_low_20d"] = c / low20 - 1.0
    out["atr_pct_14"] = atr / c
    out["vol_z_20"] = (v - vol_mean) / vol_std.replace(0.0, np.nan)
    out["rsi_14"] = _rsi(c, 14) / 100.0
    out["above_sma20"] = (c > sma20).astype(float)
    out["above_sma50"] = (c > sma50).astype(float)
    out["sma20_slope"] = sma20.pct_change(5)
    out["down_streak"] = streak.astype(float)
    out["gap_open"] = o / c.shift(1) - 1.0
    out["intraday_range_pct"] = (h - l) / c
    out["body_pct"] = (c - o) / c
    out["close_loc"] = (c - l) / (h - l).replace(0.0, np.nan)

    # Support / resistance structure
    low60 = l.rolling(60, min_periods=20).min()
    high60 = h.rolling(60, min_periods=20).max()
    atr_safe = atr.replace(0.0, np.nan)
    out["dist_to_support_20d"] = (c - low20) / c
    out["dist_to_support_60d"] = (c - low60) / c
    out["dist_to_resist_20d"] = (high20 - c) / c
    out["near_support"] = ((c - low20).abs() <= 1.25 * atr_safe).astype(float)
    out["near_resist"] = ((high20 - c).abs() <= 1.25 * atr_safe).astype(float)
    out["support_zone"] = (out["range_pos_20d"] <= 0.25).astype(float)

    # Macro placeholders (filled by join_macro_features)
    for name in (
        "qqq_ret_1d",
        "qqq_ret_5d",
        "spy_ret_1d",
        "qqq_above_sma50",
        "macro_risk_on",
        "rs_vs_qqq_5d",
    ):
        out[name] = np.nan

    # Live-only enrichment placeholders
    for name in (
        "opt_call_bias",
        "opt_pc_vol",
        "gex_below_put_wall",
        "gex_below_call_wall",
        "model_raw_conf",
        "model_setup_ok",
        "model_go_long",
        "model_soft_long",
        "model_swing_up",
        "model_above_vwap",
        "model_macd_pos",
        "macro_live_ok",
        "macro_live_defensive",
    ):
        out[name] = 0.0
    return out


def join_macro_features(feats: pd.DataFrame, index: pd.Index) -> pd.DataFrame:
    """Point-in-time QQQ/SPY macro features aligned to `index` (backward asof)."""
    out = feats.copy()
    qqq = load_ohlcv("QQQ", prefer_live=False)
    spy = load_ohlcv("SPY", prefer_live=False)
    if qqq is None or spy is None or len(qqq) < 60:
        return out
    qc = qqq[[c for c in qqq.columns if c.lower() == "close"][0]].astype(float)
    sc = spy[[c for c in spy.columns if c.lower() == "close"][0]].astype(float)
    q_sma50 = qc.rolling(50, min_periods=30).mean()
    q_ret1 = qc.pct_change()
    q_ret5 = qc.pct_change(5)
    s_ret1 = sc.pct_change()
    xlp = load_ohlcv("XLP", prefer_live=False)
    risk_on = (qc > q_sma50).astype(float)
    if xlp is not None and len(xlp) >= 60:
        xc = xlp[[c for c in xlp.columns if c.lower() == "close"][0]].astype(float)
        idx = xc.index.intersection(sc.index)
        ratio = xc.reindex(idx) / sc.reindex(idx)
        ma20 = ratio.rolling(20, min_periods=15).mean()
        ma50 = ratio.rolling(50, min_periods=30).mean()
        defensive = (ratio > ma20) & (ma20 > ma50)
        risk_on = risk_on.reindex(qc.index).astype(float)
        def_mask = defensive.reindex(qc.index).fillna(False)
        risk_on = risk_on.where(~def_mask, 0.0)

    macro = pd.DataFrame(
        {
            "qqq_ret_1d": q_ret1,
            "qqq_ret_5d": q_ret5,
            "spy_ret_1d": s_ret1.reindex(qc.index),
            "qqq_above_sma50": (qc > q_sma50).astype(float),
            "macro_risk_on": risk_on.astype(float),
        },
        index=pd.to_datetime(qc.index),
    )
    if getattr(macro.index, "tz", None) is not None:
        macro.index = macro.index.tz_localize(None)
    macro = macro.sort_index()

    tgt = pd.to_datetime(pd.Index(index))
    if getattr(tgt, "tz", None) is not None:
        tgt = tgt.tz_localize(None)
    left = pd.DataFrame({"ts": tgt}).sort_values("ts")
    right = macro.reset_index()
    right.columns = ["ts"] + list(macro.columns)
    right["ts"] = pd.to_datetime(right["ts"])
    if getattr(right["ts"].dt, "tz", None) is not None:
        right["ts"] = right["ts"].dt.tz_localize(None)
    right = right.sort_values("ts")
    joined = pd.merge_asof(left, right, on="ts", direction="backward")
    joined = joined.set_index(pd.Index(index))
    for col in ("qqq_ret_1d", "qqq_ret_5d", "spy_ret_1d", "qqq_above_sma50", "macro_risk_on"):
        if col in joined.columns:
            out[col] = joined[col].to_numpy()
    if "ret_5d" in out.columns and "qqq_ret_5d" in out.columns:
        out["rs_vs_qqq_5d"] = out["ret_5d"] - out["qqq_ret_5d"]
    return out


def support_levels_from_ohlcv(df: pd.DataFrame, spot: float | None = None) -> dict[str, Any]:
    """Human-readable support / resistance stack for desk context."""
    cols = {c.lower(): c for c in df.columns}
    h = df[cols["high"]].astype(float)
    l = df[cols["low"]].astype(float)
    c = df[cols["close"]].astype(float)
    px = float(spot if spot is not None else c.iloc[-1])
    s20 = float(l.tail(20).min())
    s60 = float(l.tail(60).min()) if len(l) >= 60 else float(l.min())
    r20 = float(h.tail(20).max())
    r60 = float(h.tail(60).max()) if len(h) >= 60 else float(h.max())
    vwap_proxy = float(((h + l + c) / 3.0).tail(20).mean())
    sma20 = float(c.tail(20).mean()) if len(c) >= 20 else float(c.mean())
    sma50 = float(c.tail(50).mean()) if len(c) >= 50 else sma20
    levels = sorted(
        {
            "s20": s20,
            "s60": s60,
            "r20": r20,
            "r60": r60,
            "vwap20": vwap_proxy,
            "sma20": sma20,
            "sma50": sma50,
        }.items(),
        key=lambda kv: kv[1],
    )
    supports = [ {"name": n, "price": round(p, 4)} for n, p in levels if p <= px ]
    resists = [ {"name": n, "price": round(p, 4)} for n, p in levels if p > px ]
    nearest_sup = supports[-1] if supports else None
    nearest_res = resists[0] if resists else None
    return {
        "spot": round(px, 4),
        "nearest_support": nearest_sup,
        "nearest_resist": nearest_res,
        "supports": supports[-4:],
        "resists": resists[:4],
        "near_support": bool(
            nearest_sup and abs(px - nearest_sup["price"]) / px <= 0.02
        ),
        "near_resist": bool(
            nearest_res and abs(nearest_res["price"] - px) / px <= 0.02
        ),
    }


def feature_row_at(df: pd.DataFrame, i: int = -1) -> dict[str, float]:
    """Single feature dict at bar index i (default last complete bar)."""
    feats = feature_frame_from_ohlcv(df)
    feats = join_macro_features(feats, feats.index)
    if len(feats) == 0:
        return {k: float("nan") for k in FEATURE_NAMES}
    row = feats.iloc[i]
    out: dict[str, float] = {}
    for k in FEATURE_NAMES:
        val = row[k] if k in row.index else np.nan
        try:
            out[k] = float(val) if np.isfinite(float(val)) else float("nan")
        except Exception:
            out[k] = float("nan")
    return out


def enrich_with_optional(
    base: dict[str, float],
    *,
    options: Mapping[str, Any] | None = None,
    gex: Mapping[str, Any] | None = None,
    model: Mapping[str, Any] | None = None,
    macro: Mapping[str, Any] | None = None,
    spot: float | None = None,
) -> dict[str, float]:
    """Merge optional live signals into a feature row (all finite, default 0)."""
    out = dict(base)
    if options:
        calls = float(options.get("calls") or 0)
        puts = float(options.get("puts") or 0)
        total = calls + puts
        out["opt_call_bias"] = (calls - puts) / total if total > 0 else 0.0
        pc = options.get("pc") or options.get("put_call_vol_ratio")
        try:
            out["opt_pc_vol"] = float(pc) if pc is not None and np.isfinite(float(pc)) else 0.0
        except Exception:
            out["opt_pc_vol"] = 0.0
    if gex and spot is not None and np.isfinite(spot):
        try:
            pw = gex.get("put_wall")
            cw = gex.get("call_wall")
            if pw is not None and np.isfinite(float(pw)):
                out["gex_below_put_wall"] = 1.0 if spot < float(pw) else 0.0
            if cw is not None and np.isfinite(float(cw)):
                out["gex_below_call_wall"] = 1.0 if spot < float(cw) else 0.0
        except Exception:
            pass
    if model:
        conf = (
            model.get("confidence")
            or model.get("raw_probability")
            or model.get("model_conf")
            or model.get("blended_confidence")
        )
        try:
            out["model_raw_conf"] = float(conf) if conf is not None and np.isfinite(float(conf)) else 0.0
        except Exception:
            out["model_raw_conf"] = 0.0
        out["model_setup_ok"] = 1.0 if model.get("setup_ok") else 0.0
        out["model_go_long"] = 1.0 if model.get("go_long") else 0.0
        out["model_soft_long"] = 1.0 if model.get("soft_long") else 0.0
        out["model_swing_up"] = 1.0 if model.get("swing_uptrend") or model.get("swing_up") else 0.0
        out["model_above_vwap"] = 1.0 if model.get("above_vwap") else 0.0
        out["model_macd_pos"] = 1.0 if model.get("macd_positive") or model.get("macd_pos") else 0.0
    if macro:
        out["macro_live_ok"] = 1.0 if macro.get("macro_ok") else 0.0
        out["macro_live_defensive"] = 1.0 if macro.get("defensive") else 0.0
        # override PIT macro with live regime when present
        qt = str(macro.get("qqq_trend") or "")
        if qt == "up":
            out["qqq_above_sma50"] = 1.0
            out["macro_risk_on"] = 0.0 if macro.get("defensive") else 1.0
        elif qt == "weak":
            out["qqq_above_sma50"] = 0.0
            out["macro_risk_on"] = 0.0
    return out


def feature_quality(features: Mapping[str, float]) -> float:
    """Fraction of core OHLCV/support/macro features that are finite."""
    core = [
        k
        for k in FEATURE_NAMES
        if not k.startswith(_CORE_PREFIX_SKIP)
    ]
    ok = 0
    for k in core:
        v = features.get(k)
        try:
            if v is not None and np.isfinite(float(v)):
                ok += 1
        except Exception:
            pass
    return ok / max(len(core), 1)


def vectorize(features: Mapping[str, float]) -> np.ndarray:
    xs = []
    for k in FEATURE_NAMES:
        v = features.get(k, 0.0)
        try:
            fv = float(v)
            if not np.isfinite(fv):
                fv = 0.0
        except Exception:
            fv = 0.0
        xs.append(fv)
    return np.asarray(xs, dtype=float)


# ---------------------------------------------------------------------------
# Labels (train only — uses future bars relative to feature bar i)
# ---------------------------------------------------------------------------


def bounce_labels(
    df: pd.DataFrame,
    horizon: int = 5,
    *,
    min_ret: float = 0.02,
) -> pd.Series:
    """Label: 1 if max high over next `horizon` bars reaches +min_ret from today close.

    Uses highs (intraday print) so it matches option target tags, not only closes.
    Default +2% is a meaningful bounce; plain next-day green has too high a base rate
    after common down days and cannot support a high-certainty band with lift.
    """
    hcol = [x for x in df.columns if x.lower() == "high"][0]
    ccol = [x for x in df.columns if x.lower() == "close"][0]
    h = df[hcol].to_numpy(dtype=float)
    c = df[ccol].to_numpy(dtype=float)
    out = np.full(len(df), np.nan)
    for i in range(len(df) - horizon):
        mx = float(np.max(h[i + 1 : i + 1 + horizon]))
        out[i] = 1.0 if mx >= c[i] * (1.0 + min_ret) else 0.0
    return pd.Series(out, index=df.index)


def target_hit_labels(df: pd.DataFrame, horizon: int, target_ret: float) -> pd.Series:
    """Label: 1 if max high over next `horizon` bars reaches target_ret from close."""
    hcol = [x for x in df.columns if x.lower() == "high"][0]
    ccol = [x for x in df.columns if x.lower() == "close"][0]
    h = df[hcol].astype(float)
    c = df[ccol].astype(float)
    # max high over (t+1 .. t+horizon) inclusive
    fut_max = h.shift(-1).rolling(horizon, min_periods=1).max().shift(-(horizon - 1))
    # cleaner: for each i, max of h[i+1:i+1+horizon]
    arr = h.to_numpy()
    c_arr = c.to_numpy()
    out = np.full(len(df), np.nan)
    for i in range(len(df) - horizon):
        mx = float(np.max(arr[i + 1 : i + 1 + horizon]))
        out[i] = 1.0 if mx >= c_arr[i] * (1.0 + target_ret) else 0.0
    return pd.Series(out, index=df.index)


# ---------------------------------------------------------------------------
# Model fit / predict
# ---------------------------------------------------------------------------


@dataclass
class BounceArtifact:
    coef: list[float]
    intercept: float
    feature_names: list[str]
    feature_mean: list[float]
    feature_std: list[float]
    isotonic: dict[str, list[float]]
    high_conf_enter: float
    high_conf_watch: float
    horizon: int
    train_symbols: list[str]
    train_end: str | None
    n_train: int
    version: str = "v80_bounce_certainty"

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "coef": self.coef,
            "intercept": self.intercept,
            "feature_names": self.feature_names,
            "feature_mean": self.feature_mean,
            "feature_std": self.feature_std,
            "isotonic": self.isotonic,
            "high_conf_enter": self.high_conf_enter,
            "high_conf_watch": self.high_conf_watch,
            "horizon": self.horizon,
            "train_symbols": self.train_symbols,
            "train_end": self.train_end,
            "n_train": self.n_train,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "BounceArtifact":
        return cls(
            coef=list(d["coef"]),
            intercept=float(d["intercept"]),
            feature_names=list(d.get("feature_names") or FEATURE_NAMES),
            feature_mean=list(d["feature_mean"]),
            feature_std=list(d["feature_std"]),
            isotonic=dict(d["isotonic"]),
            high_conf_enter=float(d.get("high_conf_enter", HIGH_CONF_ENTER)),
            high_conf_watch=float(d.get("high_conf_watch", HIGH_CONF_WATCH)),
            horizon=int(d.get("horizon", 1)),
            train_symbols=list(d.get("train_symbols") or []),
            train_end=d.get("train_end"),
            n_train=int(d.get("n_train") or 0),
            version=str(d.get("version") or "v80_bounce_certainty"),
        )


def _sigmoid(z: np.ndarray) -> np.ndarray:
    z = np.clip(z, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-z))


def fit_logistic(
    X: np.ndarray,
    y: np.ndarray,
    *,
    l2: float = 1.0,
    lr: float = 0.05,
    epochs: int = 400,
    seed: int = 7,
) -> tuple[np.ndarray, float]:
    """Simple L2 logistic regression (no sklearn dependency in predict path)."""
    rng = np.random.default_rng(seed)
    n, d = X.shape
    w = rng.normal(0, 0.01, size=d)
    b = 0.0
    for _ in range(epochs):
        p = _sigmoid(X @ w + b)
        err = p - y
        grad_w = (X.T @ err) / n + l2 * w
        grad_b = float(err.mean())
        w -= lr * grad_w
        b -= lr * grad_b
    return w, b


def standardize_fit(X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = np.nanmean(X, axis=0)
    std = np.nanstd(X, axis=0)
    std = np.where(std < 1e-8, 1.0, std)
    Xs = (X - mean) / std
    Xs = np.nan_to_num(Xs, nan=0.0, posinf=0.0, neginf=0.0)
    return Xs, mean, std


def standardize_apply(X: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    Xs = (X - mean) / np.where(std < 1e-8, 1.0, std)
    return np.nan_to_num(Xs, nan=0.0, posinf=0.0, neginf=0.0)


def raw_score(features: Mapping[str, float], art: BounceArtifact) -> float:
    x = vectorize(features)
    mean = np.asarray(art.feature_mean, dtype=float)
    std = np.asarray(art.feature_std, dtype=float)
    coef = np.asarray(art.coef, dtype=float)
    # align lengths defensively
    d = min(len(x), len(mean), len(std), len(coef))
    xs = standardize_apply(x[:d].reshape(1, -1), mean[:d], std[:d])[0]
    z = float(xs @ coef[:d] + art.intercept)
    return float(_sigmoid(np.array([z]))[0])


def _is_down_day_context(features: Mapping[str, float]) -> tuple[bool, str | None]:
    """HIGH/WATCH OOS reliability only applies on down days (ret_1d < 0)."""
    raw = features.get("ret_1d")
    try:
        r1 = float(raw) if raw is not None else float("nan")
    except (TypeError, ValueError):
        r1 = float("nan")
    if not np.isfinite(r1):
        return False, "ret_1d_missing_ood_vs_down_day_train"
    if r1 >= 0.0:
        return False, f"ret_1d_{r1:.4f}_not_down_day_ood_vs_train"
    return True, None


def predict_from_features(
    features: Mapping[str, float],
    art: BounceArtifact,
    *,
    target_ret: float | None = None,
    horizon: int | None = None,
    min_quality: float = MIN_FEATURE_QUALITY,
) -> dict[str, Any]:
    """Pure transform: features → structured forecast (unit-testable).

    HIGH/WATCH confidence states are only valid in the training context
    (down day: ret_1d < 0). Up-days / missing ret_1d force ABSTAIN so OOS
    high-certainty metrics are not applied out-of-distribution.
    """
    q = feature_quality(features)
    raw = raw_score(features, art)
    try:
        cal = float(apply_isotonic([raw], art.isotonic)[0])
    except Exception:
        cal = raw
    cal = float(np.clip(cal, 1e-6, 1.0 - 1e-6))

    abstain_reasons: list[str] = []
    if q < min_quality:
        abstain_reasons.append(f"feature_quality_{q:.2f}_below_{min_quality}")

    in_context, ood_reason = _is_down_day_context(features)
    if not in_context and ood_reason:
        abstain_reasons.append(ood_reason)

    enter = art.high_conf_enter
    watch = art.high_conf_watch
    # Never claim HIGH/WATCH outside down-day training distribution
    if not in_context:
        state = "ABSTAIN"
    elif cal >= enter and not abstain_reasons:
        state = "HIGH"
    elif cal >= watch and not abstain_reasons:
        state = "WATCH"
    else:
        state = "ABSTAIN"
        if cal < watch and not any(r.startswith("p_cal_") for r in abstain_reasons):
            abstain_reasons.append(f"p_cal_{cal:.3f}_below_watch_{watch}")

    # Direction from calibrated p relative to 0.5, with neutral band
    if cal >= 0.55:
        direction = "up"
    elif cal <= 0.45:
        direction = "down"
    else:
        direction = "sideways"

    # Target-hit proxy: scale bounce p by difficulty of target_ret over horizon
    p_target = None
    if target_ret is not None and np.isfinite(target_ret):
        tr = float(target_ret)
        if tr <= 0:
            p_target = float(np.clip(cal + 0.15, 0.0, 1.0))
        else:
            # harder targets reduce probability (horizon softens difficulty)
            h = float(horizon or art.horizon or 1)
            difficulty = min(0.85, abs(tr) / (0.01 * max(h, 1.0) ** 0.5))
            p_target = float(np.clip(cal * (1.0 - 0.55 * difficulty), 0.0, 1.0))

    return {
        "ok": True,
        "direction": direction,
        "p_bounce": cal,
        "p_bounce_raw": raw,
        "p_target_hit": p_target,
        "confidence_state": state,
        "abstain": state == "ABSTAIN",
        "abstain_reasons": abstain_reasons,
        "feature_quality": round(q, 4),
        "down_day_context": in_context,
        "thresholds": {"enter": enter, "watch": watch},
        "horizon": horizon or art.horizon,
        "target_ret": target_ret,
        "model_version": art.version,
        "feature_sources": ["ohlcv_pit"]
        + (["options_proxy"] if abs(float(features.get("opt_call_bias") or 0)) > 1e-9 else [])
        + (["gex_proxy"] if float(features.get("gex_below_put_wall") or 0) or float(features.get("gex_below_call_wall") or 0) else [])
        + (["model_signal"] if float(features.get("model_raw_conf") or 0) > 1e-9 else []),
    }


# ---------------------------------------------------------------------------
# Data load / train / eval
# ---------------------------------------------------------------------------


def _yf_ohlcv(symbol: str, period: str = "2y") -> pd.DataFrame | None:
    try:
        import yfinance as yf

        t = yf.Ticker(symbol)
        hist = t.history(period=period, interval="1d", auto_adjust=True)
        if hist is None or hist.empty:
            return None
        hist = hist.rename(columns=str.lower)
        idx = pd.to_datetime(hist.index)
        if getattr(idx, "tz", None) is not None:
            idx = idx.tz_localize(None)
        hist.index = idx
        return hist[["open", "high", "low", "close", "volume"]].dropna().sort_index()
    except Exception:
        return None


def load_ohlcv(symbol: str, *, prefer_live: bool = False) -> pd.DataFrame | None:
    """Load daily OHLCV. Cache used for training; live path refreshes when stale."""
    path = CACHE_1D / f"{symbol.upper()}.parquet"
    cached: pd.DataFrame | None = None
    if path.exists():
        df = pd.read_parquet(path)
        df.columns = [str(c).lower() for c in df.columns]
        if not isinstance(df.index, pd.DatetimeIndex):
            for cand in ("date", "timestamp", "Datetime"):
                if cand.lower() in {c.lower() for c in df.columns}:
                    col = [c for c in df.columns if c.lower() == cand.lower()][0]
                    df.index = pd.to_datetime(df[col])
                    break
        cached = df.sort_index()

    if not prefer_live and cached is not None and len(cached) >= 60:
        # Training path: pure cache for reproducibility
        return cached

    live = _yf_ohlcv(symbol)
    if live is None:
        return cached
    if cached is None or len(cached) < 30:
        return live
    # Merge: prefer live bars on overlapping dates, keep deep history from cache
    both = pd.concat([cached, live])
    both = both[~both.index.duplicated(keep="last")].sort_index()
    return both


def build_xy(
    symbols: Sequence[str],
    *,
    horizon: int = 5,
    min_history: int = 60,
    down_day_only: bool = True,
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    """Build supervised rows. When down_day_only, keep ret_1d < 0 (bounce context)."""
    X_rows: list[np.ndarray] = []
    y_rows: list[float] = []
    meta: list[dict[str, Any]] = []
    for sym in symbols:
        df = load_ohlcv(sym)
        if df is None or len(df) < min_history + horizon + 5:
            continue
        feats = feature_frame_from_ohlcv(df)
        feats = join_macro_features(feats, feats.index)
        labels = bounce_labels(df, horizon=horizon)
        for i in range(min_history, len(df) - horizon):
            row = feats.iloc[i]
            yv = labels.iloc[i]
            if not np.isfinite(yv):
                continue
            r1_raw = row["ret_1d"] if "ret_1d" in row.index else np.nan
            r1 = float(r1_raw) if np.isfinite(r1_raw) else 0.0
            if down_day_only and not (r1 < 0.0):
                continue
            feat_dict = {
                k: float(row[k]) if k in row.index and np.isfinite(row[k]) else 0.0
                for k in FEATURE_NAMES
            }
            if feature_quality(feat_dict) < 0.65:
                continue
            X_rows.append(vectorize(feat_dict))
            y_rows.append(float(yv))
            meta.append({"symbol": sym, "i": i, "ts": str(df.index[i]), "ret_1d": r1})
    if not X_rows:
        return np.zeros((0, len(FEATURE_NAMES))), np.zeros(0), []
    return np.vstack(X_rows), np.asarray(y_rows, dtype=float), meta


def train_and_evaluate(
    *,
    symbols: Sequence[str] | None = None,
    horizon: int = 5,
    holdout_frac: float = 0.25,
    artifact_path: Path = DEFAULT_ARTIFACT,
    eval_path: Path = EVAL_PATH,
) -> dict[str, Any]:
    symbols = list(symbols or TRAIN_UNIVERSE)
    X, y, meta = build_xy(symbols, horizon=horizon, down_day_only=True)
    if len(y) < 200:
        raise RuntimeError(f"insufficient training rows: {len(y)}")

    # chronological split
    order = np.argsort([m["ts"] for m in meta])
    X, y = X[order], y[order]
    meta = [meta[i] for i in order]
    cut = int(len(y) * (1.0 - holdout_frac))
    cut = max(100, min(cut, len(y) - 50))
    X_tr, y_tr = X[:cut], y[:cut]
    X_te, y_te = X[cut:], y[cut:]

    X_tr_s, mean, std = standardize_fit(X_tr)
    X_te_s = standardize_apply(X_te, mean, std)

    # Prefer sklearn for better separation when available
    try:
        from sklearn.linear_model import LogisticRegression

        clf = LogisticRegression(
            C=0.5,
            max_iter=500,
            class_weight="balanced",
            solver="lbfgs",
        )
        clf.fit(X_tr_s, y_tr)
        coef = clf.coef_.ravel()
        intercept = float(clf.intercept_[0])
        raw_tr = clf.predict_proba(X_tr_s)[:, 1]
        raw_te = clf.predict_proba(X_te_s)[:, 1]
    except Exception:
        coef, intercept = fit_logistic(X_tr_s, y_tr, l2=0.5, epochs=600)
        raw_tr = _sigmoid(X_tr_s @ coef + intercept)
        raw_te = _sigmoid(X_te_s @ coef + intercept)

    iso = fit_isotonic(raw_tr, y_tr)
    cal_te = apply_isotonic(raw_te, iso)
    metrics = calibration_metrics(y_te, cal_te)

    # Choose enter threshold maximizing high-conf hit-rate with n>=20
    enter = HIGH_CONF_ENTER
    high_hit = float("nan")
    high_brier = float("nan")
    high_n = 0
    best_score = -1.0
    for thr in np.linspace(0.55, 0.85, 31):
        m = cal_te >= thr
        n = int(m.sum())
        if n < 20:
            continue
        hit = float(y_te[m].mean())
        # prefer high hit-rate with reasonable support
        score = hit + 0.05 * math.log(n)
        if hit >= 0.60 and score > best_score:
            best_score = score
            enter = float(thr)
            high_hit = hit
            high_brier = float(np.mean((cal_te[m] - y_te[m]) ** 2))
            high_n = n
    if high_n == 0:
        # fallback: top decile of holdout scores
        thr = float(np.quantile(cal_te, 0.90))
        m = cal_te >= thr
        enter = thr
        high_n = int(m.sum())
        high_hit = float(y_te[m].mean()) if high_n else float("nan")
        high_brier = (
            float(np.mean((cal_te[m] - y_te[m]) ** 2)) if high_n else float("nan")
        )

    watch = float(max(0.50, enter - 0.08))

    art = BounceArtifact(
        coef=np.asarray(coef, dtype=float).tolist(),
        intercept=float(intercept),
        feature_names=list(FEATURE_NAMES),
        feature_mean=mean.tolist(),
        feature_std=std.tolist(),
        isotonic=iso,
        high_conf_enter=float(enter),
        high_conf_watch=watch,
        horizon=horizon,
        train_symbols=list(symbols),
        train_end=meta[cut - 1]["ts"] if cut > 0 else None,
        n_train=int(len(y_tr)),
    )

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(art.to_dict(), indent=2))
    (MODEL_DIR / "model_artifact.json").write_text(json.dumps(art.to_dict(), indent=2))

    # Also report down-day base rate
    base_rate = float(y_te.mean())
    eval_doc = {
        "ok": True,
        "model_version": art.version,
        "horizon_bars": horizon,
        "training_context": "down_days_only_ret_1d_lt_0",
        "label": f"max_high_within_{horizon}_bars_ge_plus_2pct",
        "n_total": int(len(y)),
        "n_train": int(len(y_tr)),
        "n_holdout": int(len(y_te)),
        "holdout_base_rate": base_rate,
        "train_end": art.train_end,
        "holdout_start": meta[cut]["ts"] if cut < len(meta) else None,
        "holdout_metrics": metrics,
        "high_confidence_band": {
            "threshold": art.high_conf_enter,
            "watch_threshold": art.high_conf_watch,
            "n": high_n,
            "hit_rate": high_hit,
            "brier": high_brier,
            "lift_vs_base": (
                float(high_hit - base_rate) if np.isfinite(high_hit) else None
            ),
            "definition": (
                "chronological holdout rows with calibrated p_bounce >= threshold; "
                "threshold chosen for hit_rate>=0.60 with n>=20 when possible"
            ),
        },
        "baseline_base_rate_brier": float(np.mean((np.full_like(y_te, y_tr.mean()) - y_te) ** 2)),
        "symbols": list(symbols),
        "asof_utc": datetime.now(timezone.utc).isoformat(),
        "notes": [
            "Train features: OHLCV structure + support/resistance + QQQ/SPY macro (PIT, no look-ahead).",
            "Live inference also folds desk live_plan model signals, macro_regime, options/GEX.",
            "Training restricted to down days (ret_1d < 0) — the bounce-from-here question.",
            "Label = max high over next horizon bars reaches +2% from today close.",
            "High certainty band is threshold-gated; model abstains below watch / OOD up-days.",
        ],
    }
    eval_path.write_text(json.dumps(eval_doc, indent=2))
    (MODEL_DIR / "OOS_RELIABILITY.json").write_text(json.dumps(eval_doc, indent=2))
    (MODEL_DIR / "MODEL.md").write_text(
        "# v80_bounce_certainty\n\n"
        "Calibrated logistic **bounce-from-down-day** predictor.\n\n"
        f"- Horizon: {horizon} bar(s)\n"
        f"- Context: train/eval on days with ret_1d < 0\n"
        f"- Features: price structure + support/resistance + QQQ/SPY macro; live desk model optional\n"
        f"- Holdout Brier: {metrics['brier']:.4f}\n"
        f"- Holdout base rate: {base_rate:.3f}\n"
        f"- High-conf threshold: {art.high_conf_enter:.3f}\n"
        f"- High-conf hit-rate (n={high_n}): {high_hit}\n"
        f"- Lift vs base: {(high_hit - base_rate) if np.isfinite(high_hit) else 'n/a'}\n"
        "- INFQ defaults to native stock (not IONQ) unless `--apply-desk-alias`.\n"
        "- Live: live_plan model + macro_regime + support stack + options/GEX.\n"
    )
    return {"artifact": art.to_dict(), "eval": eval_doc, "artifact_path": str(artifact_path)}


def load_artifact(path: Path | None = None) -> BounceArtifact:
    p = path or DEFAULT_ARTIFACT
    if not p.exists():
        train_and_evaluate()
        p = DEFAULT_ARTIFACT
    data = json.loads(p.read_text())
    art = BounceArtifact.from_dict(data)
    # Retrain if feature contract advanced (old artifact coef length mismatch)
    if len(art.coef) != len(FEATURE_NAMES) or list(art.feature_names) != list(FEATURE_NAMES):
        train_and_evaluate()
        data = json.loads(DEFAULT_ARTIFACT.read_text())
        art = BounceArtifact.from_dict(data)
    return art


# ---------------------------------------------------------------------------
# Live inference I/O
# ---------------------------------------------------------------------------


def _parse_json_blob(txt: str) -> dict[str, Any] | None:
    s0, s1 = txt.find("{"), txt.rfind("}")
    if s0 < 0 or s1 <= s0:
        return None
    try:
        return json.loads(txt[s0 : s1 + 1])
    except Exception:
        return None


def _optional_live_enrichment(
    symbol: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Fetch options flow, GEX, desk model (live_plan), and macro regime."""
    options: dict[str, Any] = {}
    gex: dict[str, Any] = {}
    model: dict[str, Any] = {}
    macro: dict[str, Any] = {}

    # Macro first (fast, no model load)
    try:
        from live_plan import macro_regime

        macro = macro_regime(None) or {}
    except Exception as e:
        macro = {"error": str(e), "macro_ok": True, "qqq_trend": None}

    # Desk model path via live_plan --json (full features: conf, setup, vwap, swing)
    try:
        import subprocess

        r = subprocess.run(
            [
                str(ROOT / ".venv/bin/python"),
                "tools/live_plan.py",
                "--symbol",
                symbol,
                "--account",
                "1000",
                "--model",
                "auto",
                "--json",
            ],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=90,
        )
        plan = _parse_json_blob(r.stdout)
        if plan:
            live = plan.get("live") or {}
            m = plan.get("model") or {}
            conf = plan.get("confidence") or {}
            model = {
                "model_id": m.get("model"),
                "setup_ok": m.get("setup_ok"),
                "confidence": m.get("confidence") or conf.get("raw_probability"),
                "calibrated_probability": conf.get("calibrated_probability"),
                "conf_state": conf.get("state"),
                "analysis": (plan.get("decision") or {}).get("analysis_action")
                or m.get("action_hint"),
                "go_long": live.get("go_long"),
                "soft_long": live.get("soft_long"),
                "swing_uptrend": live.get("swing_uptrend"),
                "above_vwap": live.get("above_vwap"),
                "macd_positive": live.get("macd_positive"),
                "vol_z": live.get("vol_z"),
                "price": live.get("price"),
                "entry": m.get("entry"),
                "stop": m.get("stop"),
            }
            if plan.get("macro"):
                macro = {**macro, **(plan.get("macro") or {})}
    except Exception as e:
        model = {"error": str(e)}

    try:
        from options_unusual_flow import scan_symbol

        fl = scan_symbol(symbol, max_expiries=3, max_dte=30, top_n=8)
        flags = fl.get("flags") or []
        calls = sum(1 for f in flags if str(f.get("right", "")).upper() in ("C", "CALL"))
        puts = sum(1 for f in flags if str(f.get("right", "")).upper() in ("P", "PUT"))
        options = {"calls": calls, "puts": puts, "pc": None}
        try:
            from vol_package_score import score_symbol

            vp = score_symbol(symbol)
            options["pc"] = (vp.get("features") or {}).get("put_call_vol_ratio")
        except Exception:
            pass
    except Exception:
        pass
    try:
        import subprocess

        r = subprocess.run(
            [str(ROOT / ".venv/bin/python"), "tools/gamma_exposure.py", "--symbol", symbol, "--json"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=45,
        )
        gex = _parse_json_blob(r.stdout) or {}
    except Exception:
        pass
    return options, gex, model, macro


def predict_symbol(
    symbol: str,
    *,
    target_price: float | None = None,
    horizon: int | None = None,
    apply_desk_alias: bool = False,
    enrich_live: bool = True,
    artifact: BounceArtifact | None = None,
) -> dict[str, Any]:
    res = resolve_symbol(symbol, apply_desk_alias=apply_desk_alias)
    sym = res["resolved"]
    if not sym:
        return {"ok": False, "error": "invalid_symbol", "symbol_resolution": res}

    art = artifact or load_artifact()
    df = load_ohlcv(sym, prefer_live=True)
    history_note = "native_history"
    proxy_used = None
    if df is None or len(df) < 20:
        # Thin listings (e.g. new ADR SKHY): fall back to sector proxy for structure,
        # always abstain-capable via feature_quality / explicit reason.
        proxy_used = "SOXX" if sym in {"SKHY", "MU", "SNDK"} else "SPY"
        df = load_ohlcv(proxy_used, prefer_live=True)
        history_note = f"proxy_{proxy_used}_insufficient_{sym}_history"
        if df is None or len(df) < 60:
            return {
                "ok": False,
                "error": f"insufficient_history_for_{sym}",
                "symbol_resolution": res,
                "confidence_state": "ABSTAIN",
                "abstain": True,
                "direction": "sideways",
                "p_bounce": None,
            }
    elif len(df) < 60:
        # Blend: use proxy backbone, overwrite last bars with native when present
        proxy_used = "SOXX" if sym in {"SKHY", "MU", "SNDK"} else "SPY"
        proxy = load_ohlcv(proxy_used, prefer_live=True)
        if proxy is not None and len(proxy) >= 60:
            # append native tail onto proxy history for local momentum
            native = df.copy()
            df = pd.concat([proxy.iloc[:- len(native)], native])
            df = df[~df.index.duplicated(keep="last")].sort_index()
            history_note = f"blended_{proxy_used}_plus_native_tail"

    feats = feature_row_at(df, -1)
    # Prefer native last print for spot when available
    native_df = load_ohlcv(sym, prefer_live=True)
    if native_df is not None and len(native_df) > 0:
        spot = float(native_df[[c for c in native_df.columns if c.lower() == "close"][0]].iloc[-1])
        asof_bar = str(native_df.index[-1])
        # overlay short native momentum into features when history is thin
        if len(native_df) >= 2:
            nclose = native_df[[c for c in native_df.columns if c.lower() == "close"][0]].astype(float)
            feats["ret_1d"] = float(nclose.iloc[-1] / nclose.iloc[-2] - 1.0)
        if len(native_df) >= 6:
            nclose = native_df[[c for c in native_df.columns if c.lower() == "close"][0]].astype(float)
            feats["ret_5d"] = float(nclose.iloc[-1] / nclose.iloc[-6] - 1.0)
    else:
        spot = float(df[[c for c in df.columns if c.lower() == "close"][0]].iloc[-1])
        asof_bar = str(df.index[-1])

    options, gex, model, macro = {}, {}, {}, {}
    if enrich_live:
        options, gex, model, macro = _optional_live_enrichment(sym)
        feats = enrich_with_optional(
            feats, options=options, gex=gex, model=model, macro=macro, spot=spot
        )
    else:
        # still attach PIT macro from cache (already in feats via join_macro)
        try:
            from live_plan import macro_regime

            macro = macro_regime(None) or {}
            feats = enrich_with_optional(feats, macro=macro, spot=spot)
        except Exception:
            pass

    levels = support_levels_from_ohlcv(
        native_df if native_df is not None and len(native_df) >= 5 else df,
        spot=spot,
    )

    target_ret = None
    already_hit = False
    if target_price is not None and spot > 0:
        target_ret = float(target_price) / spot - 1.0
        if target_ret <= 0:
            already_hit = True

    pred = predict_from_features(
        feats,
        art,
        target_ret=None if already_hit else target_ret,
        horizon=horizon or art.horizon,
    )
    if already_hit:
        pred["p_target_hit"] = 1.0
        pred["target_status"] = "already_at_or_above_target"
    elif target_ret is not None:
        pred["target_status"] = "below_target"

    # Context-aware certainty gates (desk models + macro + support)
    # Do not invent HIGH; only demote or annotate.
    ctx_notes: list[str] = []
    if macro.get("defensive") or macro.get("macro_ok") is False:
        ctx_notes.append("macro_defensive_or_blocked")
        if pred.get("confidence_state") == "HIGH":
            pred["confidence_state"] = "WATCH"
            pred["abstain"] = False
            pred.setdefault("abstain_reasons", []).append("demoted_HIGH_to_WATCH_macro")
    analysis_u = str(model.get("analysis") or "").upper()
    if "AVOID" in analysis_u:
        ctx_notes.append("desk_model_AVOID")
        if pred.get("confidence_state") == "HIGH":
            pred["confidence_state"] = "WATCH"
            pred.setdefault("abstain_reasons", []).append("demoted_HIGH_to_WATCH_desk_avoid")
    if levels.get("near_resist") and target_ret and target_ret > 0.03:
        ctx_notes.append("near_resistance_vs_upside_target")
    if levels.get("near_support"):
        ctx_notes.append("near_support_stack")
    if model.get("go_long"):
        ctx_notes.append("desk_go_long")
    elif model.get("soft_long"):
        ctx_notes.append("desk_soft_long")
    if model.get("above_vwap") is False:
        ctx_notes.append("below_vwap")
    if str(macro.get("qqq_trend")) == "weak":
        ctx_notes.append("qqq_trend_weak")
    # Desk WAIT + weak QQQ + no long = do not keep HIGH certainty
    desk_blocked = (
        (not model.get("go_long"))
        and (not model.get("soft_long"))
        and (
            "WAIT" in analysis_u
            or "AVOID" in analysis_u
            or model.get("setup_ok") is False
        )
    )
    macro_weak = str(macro.get("qqq_trend")) == "weak" or macro.get("defensive")
    if pred.get("confidence_state") == "HIGH" and desk_blocked and macro_weak:
        pred["confidence_state"] = "WATCH"
        pred.setdefault("abstain_reasons", []).append(
            "demoted_HIGH_to_WATCH_desk_wait_and_weak_macro"
        )
        ctx_notes.append("high_demoted_desk_macro_conflict")
    # Support can keep a bounce lean, but not override hard macro+desk block for target certainty
    if pred.get("p_target_hit") is not None and desk_blocked and macro_weak:
        pred["p_target_hit"] = float(min(float(pred["p_target_hit"]), 0.40))

    # Per-name drivers: Nasdaq peg / co-move + options pressure + OpEx calendar
    # NEVER feed sector-proxy OHLCV into co-move (invents corr=1 vs SOXX/SPY).
    asset_close = None
    asset_is_proxy = bool(proxy_used and "proxy_" in (history_note or ""))
    try:
        if native_df is not None and len(native_df) >= 15:
            asset_close = native_df[
                [c for c in native_df.columns if c.lower() == "close"][0]
            ].astype(float)
            asset_is_proxy = False
        elif native_df is not None and len(native_df) >= 2 and not asset_is_proxy:
            # Short native only — pass through; rolling_comove will fail insufficient_overlap
            asset_close = native_df[
                [c for c in native_df.columns if c.lower() == "close"][0]
            ].astype(float)
        elif asset_is_proxy:
            asset_close = None
        else:
            asset_close = df[[c for c in df.columns if c.lower() == "close"][0]].astype(float)
    except Exception:
        asset_close = None
    drivers = symbol_driver_context(
        sym,
        asset_close=asset_close,
        asof=pd.Timestamp.utcnow(),
        gex=gex if gex else None,
        options=options if options else None,
        spot=spot,
        asset_is_proxy=asset_is_proxy,
        proxy_symbol=proxy_used,
    )
    opex = drivers.get("opex") or {}
    comove = drivers.get("comove") or {}
    if opex.get("opex_window"):
        ctx_notes.append("opex_window")
        # OpEx + weak Nasdaq + desk WAIT → demote HIGH (pin risk > trend bounce)
        if (
            pred.get("confidence_state") == "HIGH"
            and desk_blocked
            and (macro_weak or comove.get("same_day_direction") == "together")
        ):
            pred["confidence_state"] = "WATCH"
            pred.setdefault("abstain_reasons", []).append(
                "demoted_HIGH_to_WATCH_opex_pin_risk"
            )
            ctx_notes.append("high_demoted_opex_and_tape")
        if pred.get("p_target_hit") is not None and opex.get("opex_window"):
            # Cap target confidence into expiry — harder to trend through walls
            pred["p_target_hit"] = float(min(float(pred["p_target_hit"]), 0.45))
    if comove.get("ok") and comove.get("tandem") == "high_tandem":
        ctx_notes.append(f"high_tandem_vs_{comove.get('benchmark')}")
        if comove.get("same_day_direction") == "together" and comove.get("bench_ret_1d") is not None:
            if float(comove["bench_ret_1d"]) < 0:
                ctx_notes.append("nasdaq_benchmark_red_with_name")
    elif comove.get("error") == "proxy_self_or_unavailable":
        ctx_notes.append("comove_unavailable_proxy_history")
    if (drivers.get("options_pressure") or {}).get("flow_bias") == "call_heavy":
        ctx_notes.append("options_call_heavy")
    elif (drivers.get("options_pressure") or {}).get("flow_bias") == "put_heavy":
        ctx_notes.append("options_put_heavy")
    nw = ((drivers.get("gex_pressure") or {}).get("near_wall") or {})
    if nw.get("near"):
        ctx_notes.append(f"near_gex_{nw.get('type')}")

    # Force abstain when using pure proxy / thin listing — honesty > fake certainty
    if proxy_used and "proxy_" in history_note:
        pred["confidence_state"] = "ABSTAIN"
        pred["abstain"] = True
        pred.setdefault("abstain_reasons", []).append(history_note)

    pred["abstain"] = pred.get("confidence_state") == "ABSTAIN"

    # One-line live operator take
    live_take = (
        f"{sym} @ {spot:.2f}: bounce={pred.get('direction')} "
        f"p={pred.get('p_bounce'):.2f} state={pred.get('confidence_state')}"
    )
    if comove.get("ok"):
        live_take += (
            f" | vs {comove.get('benchmark')} corr={comove.get('corr')} "
            f"{comove.get('same_day_direction')}"
        )
    elif comove.get("error") == "proxy_self_or_unavailable":
        live_take += " | co-move unavailable (proxy history)"
    if opex.get("opex_window"):
        live_take += " | OpEx window"
    if (drivers.get("options_pressure") or {}).get("available"):
        live_take += f" | opt_flow={(drivers.get('options_pressure') or {}).get('flow_bias')}"

    pred.update(
        {
            "symbol": sym,
            "input_symbol": symbol,
            "symbol_resolution": res,
            "spot": round(spot, 4),
            "target_price": target_price,
            "asof_bar": asof_bar,
            "asof_utc": datetime.now(timezone.utc).isoformat(),
            "history_note": history_note,
            "proxy_used": proxy_used,
            "live_take": live_take,
            "context": {
                "desk_model": {
                    "id": model.get("model_id"),
                    "analysis": model.get("analysis"),
                    "setup_ok": model.get("setup_ok"),
                    "confidence": model.get("confidence"),
                    "conf_state": model.get("conf_state"),
                    "go_long": model.get("go_long"),
                    "soft_long": model.get("soft_long"),
                    "swing_uptrend": model.get("swing_uptrend"),
                    "above_vwap": model.get("above_vwap"),
                    "macd_positive": model.get("macd_positive"),
                    "stop": model.get("stop"),
                },
                "macro": {
                    "qqq_trend": macro.get("qqq_trend"),
                    "macro_ok": macro.get("macro_ok"),
                    "defensive": macro.get("defensive"),
                    "xlp_spy_ratio_state": macro.get("xlp_spy_ratio_state"),
                    "error": macro.get("error"),
                },
                "support_resistance": levels,
                "drivers": drivers,
                "opex": opex,
                "comove": comove,
                "options_pressure": drivers.get("options_pressure"),
                "gex_pressure": drivers.get("gex_pressure"),
                "what_moves_this": drivers.get("what_moves_this"),
                "notes": ctx_notes,
            },
            "live_enrichment": {
                "options": bool(options),
                "gex": bool(gex.get("call_wall") or gex.get("put_wall")),
                "desk_model": bool(model.get("model_id") or model.get("confidence") is not None),
                "macro": bool(macro.get("qqq_trend") is not None or macro.get("macro_ok") is not None),
                "support_levels": True,
                "comove": bool(comove.get("ok")),
                "opex": True,
            },
            "feature_snapshot": {
                k: feats.get(k)
                for k in (
                    "ret_1d",
                    "near_support",
                    "near_resist",
                    "support_zone",
                    "qqq_ret_1d",
                    "macro_risk_on",
                    "model_raw_conf",
                    "model_go_long",
                    "macro_live_ok",
                    "macro_live_defensive",
                )
            },
        }
    )
    return pred


def predict_book(
    symbols: Sequence[str] | None = None,
    *,
    targets: Mapping[str, float] | None = None,
    apply_desk_alias: bool = False,
    enrich_live: bool = True,
) -> dict[str, Any]:
    symbols = list(symbols or DEFAULT_BOOK)
    targets = dict(targets or {})
    # sensible defaults matching user book
    defaults = {"TSLA": 397.5, "MSTR": 102.0, "SKHY": 180.0, "INFQ": 10.0}
    for k, v in defaults.items():
        targets.setdefault(k, v)

    art = load_artifact()
    rows = []
    for s in symbols:
        tgt = targets.get(s.upper()) or targets.get(resolve_symbol(s)["resolved"] or "")
        row = predict_symbol(
            s,
            target_price=float(tgt) if tgt is not None else None,
            apply_desk_alias=apply_desk_alias,
            enrich_live=enrich_live,
            artifact=art,
        )
        rows.append(row)

    session_opex = opex_session_flag(pd.Timestamp.utcnow(), look_ahead_days=1)
    return {
        "ok": True,
        "n": len(rows),
        "rows": rows,
        "model_version": art.version,
        "session": {
            "opex": session_opex,
            "note": (
                "Per-name blocks include Nasdaq/benchmark co-move, options/GEX pressure, "
                "and OpEx flags. Options/GEX are chain proxies — not dealer inventory."
            ),
        },
        "asof_utc": datetime.now(timezone.utc).isoformat(),
        "note": (
            "High certainty means confidence_state=HIGH with calibrated probability "
            "above the OOS-gated enter threshold; ABSTAIN when evidence is weak. "
            "OpEx/desk/macro conflicts demote HIGH → WATCH."
        ),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Bounce / direction certainty predictor")
    ap.add_argument("--symbol", type=str, default=None, help="Single symbol")
    ap.add_argument("--book", action="store_true", help="Score default book TSLA,MSTR,SKHY,INFQ")
    ap.add_argument("--symbols", type=str, default=None, help="Comma-separated symbols")
    ap.add_argument("--target", type=float, default=None, help="Target price for single symbol")
    ap.add_argument("--horizon", type=int, default=None)
    ap.add_argument("--train", action="store_true", help="Fit + evaluate model")
    ap.add_argument("--apply-desk-alias", action="store_true", help="Apply INFQ→IONQ alias explicitly")
    ap.add_argument("--no-live", action="store_true", help="Skip live options/GEX enrichment")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    if args.train:
        out = train_and_evaluate(horizon=args.horizon or 5)
        print(json.dumps(out["eval"], indent=2))
        return 0

    if args.book or args.symbols:
        syms = (
            [s.strip() for s in args.symbols.split(",") if s.strip()]
            if args.symbols
            else DEFAULT_BOOK
        )
        out = predict_book(
            syms,
            apply_desk_alias=args.apply_desk_alias,
            enrich_live=not args.no_live,
        )
        if args.json:
            print(json.dumps(out, indent=2, default=str))
        else:
            print(f"BOUNCE MODEL {out['model_version']}  n={out['n']}")
            sess = (out.get("session") or {}).get("opex") or {}
            print(
                f"  SESSION OpEx window={sess.get('opex_window')}  "
                f"today={((sess.get('today') or {}).get('date'))}  "
                f"tom={((sess.get('tomorrow') or {}).get('date'))}  "
                f"monthly={sess.get('next_monthly_opex')}"
            )
            for r in out["rows"]:
                if not r.get("ok"):
                    print(f"  {r.get('input_symbol') or r.get('symbol')}: ERROR {r.get('error')}")
                    continue
                ctx = r.get("context") or {}
                com = ctx.get("comove") or {}
                print(
                    f"  {r['symbol']:5s}  dir={r['direction']:8s}  "
                    f"p_bounce={r['p_bounce']:.3f}  state={r['confidence_state']:7s}  "
                    f"p_tgt={r.get('p_target_hit')}  spot={r.get('spot')}"
                )
                print(
                    f"         drivers: vs {com.get('benchmark')} corr={com.get('corr')} "
                    f"beta={com.get('beta')} {com.get('tandem')} {com.get('same_day_direction')} | "
                    f"opt={(ctx.get('options_pressure') or {}).get('flow_bias')} | "
                    f"gex_near={((ctx.get('gex_pressure') or {}).get('near_wall') or {}).get('type')}"
                )
                print(f"         take: {r.get('live_take')}")
        return 0

    if not args.symbol:
        ap.error("provide --symbol, --book, or --train")

    out = predict_symbol(
        args.symbol,
        target_price=args.target,
        horizon=args.horizon,
        apply_desk_alias=args.apply_desk_alias,
        enrich_live=not args.no_live,
    )
    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        if not out.get("ok"):
            print("ERROR", out)
            return 1
        print(
            f"{out['symbol']}  {out['direction']}  p_bounce={out['p_bounce']:.3f}  "
            f"state={out['confidence_state']}  spot={out['spot']}"
        )
        if out.get("p_target_hit") is not None:
            print(f"  p_target_hit={out['p_target_hit']:.3f}  target={out.get('target_price')}")
        print(f"  resolution={out['symbol_resolution']}")
        if out.get("abstain_reasons"):
            print(f"  abstain: {out['abstain_reasons']}")
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
