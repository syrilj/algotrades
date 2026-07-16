#!/usr/bin/env python3
"""Sector money-flow scanner — where capital is rotating, and how definitive it is.

Answers (descriptive, not a validated alpha model):
  1) Where money is flowing *into* (relative + absolute strength leaders)
  2) Where money is rotating *out of* (laggards / defensive bids)
  3) Whether the move looks definitive vs noise (multi-horizon + volume + structure)
  4) What to keep in mind when trading those flows (desk notes)

Data: prefers local ``data_cache/1d/*.parquet``; falls back to yfinance.

Usage:
  .venv/bin/python tools/sector_money_flow.py
  .venv/bin/python tools/sector_money_flow.py --json
  .venv/bin/python tools/sector_money_flow.py --source local --json
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CACHE_1D = ROOT / "data_cache" / "1d"

# SPDR sectors + theme books. Semis (SOXX/SMH) are FIRST-CLASS — XLK alone
# hides SOXX→software/tech rotation (the desk's real day-flow question).
SECTOR_META: dict[str, dict[str, Any]] = {
    # --- Theme books (Arete-style; often need Yahoo if not in local cache) ---
    "SOXX": {
        "name": "Semis",
        "bucket": "semis",
        "theme": True,
        "names": ["NVDA", "AVGO", "AMD", "MU", "TSM", "ARM", "ASML", "LRCX"],
    },
    "SMH": {
        "name": "Semis (VanEck)",
        "bucket": "semis",
        "theme": True,
        "names": ["NVDA", "TSM", "AVGO", "ASML", "AMD", "MU"],
    },
    "IGV": {
        "name": "Software",
        "bucket": "software",
        "theme": True,
        "names": ["MSFT", "CRM", "ADBE", "NOW", "INTU", "PANW", "CRWD"],
    },
    "QQQ": {
        "name": "Nasdaq-100",
        "bucket": "growth",
        "theme": True,
        "names": ["NVDA", "MSFT", "AAPL", "AMZN", "META", "AVGO", "GOOGL"],
    },
    # --- Core SPDR / sector books ---
    "XLK": {
        "name": "Tech (XLK)",
        "bucket": "tech",
        "theme": False,
        "names": ["NVDA", "AAPL", "MSFT", "AVGO", "AMD", "CRM", "ORCL"],
    },
    "XLC": {
        "name": "Comm",
        "bucket": "growth",
        "theme": False,
        "names": ["META", "GOOGL", "NFLX", "DIS"],
    },
    "XLY": {
        "name": "Discretionary",
        "bucket": "growth",
        "theme": False,
        "names": ["AMZN", "TSLA", "HD", "MCD"],
    },
    "XLF": {"name": "Financials", "bucket": "cyclical", "theme": False, "names": ["JPM", "GS", "BAC", "HOOD"]},
    "XLE": {"name": "Energy", "bucket": "cyclical", "theme": False, "names": ["XOM", "CVX", "OXY"]},
    "XLI": {"name": "Industrials", "bucket": "cyclical", "theme": False, "names": ["CAT", "GE", "HON"]},
    "XLB": {"name": "Materials", "bucket": "cyclical", "theme": False, "names": ["LIN", "FCX"]},
    "XLV": {"name": "Health", "bucket": "defensive", "theme": False, "names": ["UNH", "LLY", "JNJ"]},
    "XLP": {"name": "Staples", "bucket": "defensive", "theme": False, "names": ["PG", "KO", "WMT"]},
    "XLU": {"name": "Utilities", "bucket": "defensive", "theme": False, "names": ["NEE", "DUK"]},
}

# Ratio pairs — include semis vs tech so SOXX→XLK/IGV shows up as a named rotation.
RATIO_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("XLY", "XLP", "discretionary_vs_staples"),
    ("XLK", "XLP", "tech_vs_staples"),
    ("XLY", "XLV", "discretionary_vs_health"),
    ("QQQ", "SPY", "nasdaq_vs_spy"),
    ("SOXX", "XLK", "semis_vs_tech"),
    ("SOXX", "SPY", "semis_vs_spy"),
    ("SOXX", "IGV", "semis_vs_software"),
    ("IGV", "XLK", "software_vs_tech"),
    ("SMH", "XLK", "smh_vs_tech"),
)

LOOKBACKS: tuple[int, ...] = (1, 5, 21)
# Material thresholds
MATERIAL_RS_5D = 0.008  # 0.8%
MATERIAL_RS_1D = 0.0015  # 0.15% day RS vs SPY (session signal)
MATERIAL_RET_1D = 0.004  # 0.4% day move
RVOL_CONFIRM = 1.15
DEFINITIVE_SCORE_CUT = 0.62

# Themes that should always be attempted via Yahoo when missing from local cache.
THEME_FETCH_ALWAYS = ("SOXX", "SMH", "IGV", "QQQ")

DISCLAIMER = (
    "Price/volume relative strength is a *proxy* for money flow, not dark-pool or "
    "institutional order-flow data. Descriptive research only — not a validated edge "
    "or 80% WR system. Rotation ≠ always leave equities."
)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _norm_sym(symbol: str) -> str:
    s = symbol.strip().upper().replace(".US", "").lstrip("^")
    return s


def load_ohlcv_local(symbol: str, cache_dir: Path = CACHE_1D) -> pd.DataFrame:
    """Load OHLCV from data_cache/1d. Empty if missing."""
    sym = _norm_sym(symbol)
    for name in (sym, f"{sym}.US", f"^{sym}"):
        path = cache_dir / f"{name}.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        cols = {c.lower(): c for c in df.columns}
        need = ["open", "high", "low", "close", "volume"]
        if not all(k in cols for k in need):
            # close-only tolerance
            if "close" not in cols:
                continue
            out = pd.DataFrame({"close": df[cols["close"]].astype(float)})
            out["volume"] = np.nan
            out.index = pd.to_datetime(df.index)
            if getattr(out.index, "tz", None) is not None:
                out.index = out.index.tz_localize(None)
            return out.sort_index()
        out = pd.DataFrame(
            {
                "open": df[cols["open"]].astype(float),
                "high": df[cols["high"]].astype(float),
                "low": df[cols["low"]].astype(float),
                "close": df[cols["close"]].astype(float),
                "volume": df[cols["volume"]].astype(float),
            },
            index=pd.to_datetime(df.index),
        )
        if getattr(out.index, "tz", None) is not None:
            out.index = out.index.tz_localize(None)
        return out.sort_index().dropna(subset=["close"])
    return pd.DataFrame()


def load_ohlcv_yfinance(symbols: Sequence[str], period: str = "6mo") -> dict[str, pd.DataFrame]:
    """Batch download OHLCV; returns {symbol: df}."""
    import yfinance as yf

    tickers = [_norm_sym(s) for s in symbols]
    tickers = list(dict.fromkeys(tickers))
    if not tickers:
        return {}
    raw = yf.download(
        tickers,
        period=period,
        group_by="ticker",
        auto_adjust=True,
        progress=False,
        threads=True,
    )
    out: dict[str, pd.DataFrame] = {}
    if raw is None or raw.empty:
        return out

    def _one(t: str, block: pd.DataFrame) -> pd.DataFrame:
        if block is None or block.empty:
            return pd.DataFrame()
        b = block.copy()
        b.columns = [str(c).lower() for c in b.columns]
        need = ["open", "high", "low", "close", "volume"]
        if not all(c in b.columns for c in need):
            if "close" in b.columns:
                return pd.DataFrame(
                    {"close": b["close"].astype(float), "volume": b.get("volume", np.nan)},
                    index=pd.to_datetime(b.index),
                ).dropna(subset=["close"])
            return pd.DataFrame()
        df = b[need].astype(float).dropna(subset=["close"])
        df.index = pd.to_datetime(df.index)
        if getattr(df.index, "tz", None) is not None:
            df.index = df.index.tz_localize(None)
        return df

    if len(tickers) == 1:
        t = tickers[0]
        df = _one(t, raw if not isinstance(raw.columns, pd.MultiIndex) else raw)
        if not df.empty:
            out[t] = df
        return out

    if isinstance(raw.columns, pd.MultiIndex):
        level0 = raw.columns.get_level_values(0)
        for t in tickers:
            if t not in level0:
                continue
            df = _one(t, raw[t])
            if not df.empty:
                out[t] = df
    return out


def _maybe_cache_yf(panel: Mapping[str, pd.DataFrame], cache_dir: Path = CACHE_1D) -> None:
    """Best-effort write of newly fetched theme books into data_cache/1d."""
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        return
    for sym, df in panel.items():
        if df is None or df.empty or len(df) < 30:
            continue
        path = cache_dir / f"{_norm_sym(sym)}.parquet"
        if path.exists():
            continue
        try:
            out = df.copy()
            out.index.name = "date"
            out.to_parquet(path)
        except Exception:  # noqa: BLE001
            continue


def load_panel(
    symbols: Sequence[str],
    source: str = "auto",
    cache_dir: Path = CACHE_1D,
    period: str = "6mo",
) -> dict[str, pd.DataFrame]:
    """Load OHLCV panel. source: auto|local|yfinance.

    ``auto`` always fills missing theme books (SOXX/SMH/IGV/…) via Yahoo even
    when SPDR sectors already exist locally — otherwise semis rotation is invisible.
    """
    want = [_norm_sym(s) for s in symbols]
    want = list(dict.fromkeys(want))
    panel: dict[str, pd.DataFrame] = {}

    if source in ("auto", "local"):
        for s in want:
            df = load_ohlcv_local(s, cache_dir=cache_dir)
            if not df.empty and len(df) >= 30:
                panel[s] = df

    missing = [s for s in want if s not in panel]
    # Even on "local", surface a soft warning path: still try themes if none present
    if source == "local":
        theme_missing = [s for s in THEME_FETCH_ALWAYS if s in want and s not in panel]
        if theme_missing:
            # Local-only asked, but themes are required for correct desk read —
            # fetch themes only (keep SPDR from disk).
            try:
                yf_panel = load_ohlcv_yfinance(theme_missing, period=period)
                panel.update(yf_panel)
                _maybe_cache_yf(yf_panel, cache_dir=cache_dir)
            except Exception:  # noqa: BLE001
                pass
        return panel

    if source == "yfinance" or (source == "auto" and missing):
        fetch = want if source == "yfinance" else missing
        # Ensure critical themes are always attempted on auto
        if source == "auto":
            for t in THEME_FETCH_ALWAYS:
                if t in want and t not in panel and t not in fetch:
                    fetch.append(t)
        if fetch:
            try:
                yf_panel = load_ohlcv_yfinance(fetch, period=period)
                panel.update(yf_panel)
                _maybe_cache_yf(yf_panel, cache_dir=cache_dir)
            except Exception:  # noqa: BLE001
                pass
    return panel


# ---------------------------------------------------------------------------
# Pure metrics (testable)
# ---------------------------------------------------------------------------


def ret_n(close: pd.Series, n: int) -> float:
    """Trailing n-bar simple return. NaN if insufficient history."""
    a = close.dropna()
    if len(a) < n + 1 or n < 1:
        return float("nan")
    return float(a.iloc[-1] / a.iloc[-(n + 1)] - 1.0)


def rs_n(sec: pd.Series, bench: pd.Series, n: int) -> float:
    """Relative strength = sector ret − benchmark ret over n bars."""
    joined = pd.concat([sec.rename("s"), bench.rename("b")], axis=1).dropna()
    if len(joined) < n + 1:
        return float("nan")
    return ret_n(joined["s"], n) - ret_n(joined["b"], n)


def rvol_last(volume: pd.Series, look: int = 20) -> float:
    """Last bar volume / mean prior look bars."""
    v = volume.dropna().astype(float)
    if len(v) < look + 1:
        return float("nan")
    base = float(v.iloc[-(look + 1) : -1].mean())
    if base <= 0:
        return float("nan")
    return float(v.iloc[-1] / base)


def above_ma(close: pd.Series, window: int = 20) -> bool | None:
    a = close.dropna()
    if len(a) < window:
        return None
    return bool(float(a.iloc[-1]) > float(a.tail(window).mean()))


def _sign(x: float) -> int:
    if not np.isfinite(x) or abs(x) < 1e-12:
        return 0
    return 1 if x > 0 else -1


@dataclass
class SectorFlow:
    etf: str
    name: str
    bucket: str
    ret_1d: float
    ret_5d: float
    ret_21d: float
    rs_1d: float
    rs_5d: float
    rs_21d: float
    flow_score: float  # day-weighted composite (primary rank for "today")
    week_flow_score: float  # 5d/21d composite (multi-day leadership)
    day_direction: str  # in | out | neutral — TODAY vs SPY
    flow_direction: str  # same as day_direction for desk (alias)
    week_direction: str  # multi-day leadership
    definitive: bool
    definitive_score: float
    definitive_reasons: list[str] = field(default_factory=list)
    above_ma20: bool | None = None
    rvol: float = float("nan")
    rank: int = 0
    focus_names: list[str] = field(default_factory=list)
    theme: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # JSON-safe floats
        for k, v in list(d.items()):
            if isinstance(v, float) and not np.isfinite(v):
                d[k] = None
        return d


def _weighted_mean(pairs: Sequence[tuple[float, float]]) -> float:
    parts = []
    weights = []
    for val, w in pairs:
        if np.isfinite(val):
            parts.append(val * w)
            weights.append(w)
    if not parts:
        return float("nan")
    return float(sum(parts) / sum(weights))


def flow_score(rs_1d: float, rs_5d: float, rs_21d: float, ret_1d: float, above: bool | None) -> float:
    """Day-weighted composite — answers 'where is money moving *today*'.

    1d RS dominates; 5d is context; absolute day return keeps pure relative traps honest.
    """
    base = _weighted_mean(
        (
            (rs_1d, 0.50),
            (ret_1d, 0.20),
            (rs_5d, 0.22),
            (rs_21d, 0.08),
        )
    )
    if not np.isfinite(base):
        return float("nan")
    if above is True:
        base += 0.001
    elif above is False:
        base -= 0.001
    return float(base)


def week_flow_score(rs_1d: float, rs_5d: float, rs_21d: float, above: bool | None) -> float:
    """Multi-day leadership score (less twitchy than day flow)."""
    base = _weighted_mean(((rs_5d, 0.55), (rs_21d, 0.30), (rs_1d, 0.15)))
    if not np.isfinite(base):
        return float("nan")
    if above is True:
        base += 0.001
    elif above is False:
        base -= 0.001
    return float(base)


def definitive_assessment(
    *,
    rs_1d: float,
    rs_5d: float,
    rs_21d: float,
    ret_1d: float,
    ret_5d: float,
    above: bool | None,
    rvol: float,
    direction: str,
) -> tuple[float, bool, list[str]]:
    """Score how definitive an inflow/outflow looks. Returns (score, flag, reasons)."""
    if direction == "neutral":
        return 0.0, False, ["neutral flow — no directional claim"]

    reasons: list[str] = []
    score = 0.0
    want = 1 if direction == "in" else -1

    signs = [_sign(rs_1d), _sign(rs_5d), _sign(rs_21d)]
    agree = sum(1 for s in signs if s == want)
    if agree == 3:
        score += 0.40
        reasons.append("1d/5d/21d RS all agree with direction")
    elif agree == 2:
        score += 0.22
        reasons.append("2 of 3 RS horizons agree")
    else:
        reasons.append("horizons disagree — treat as noise until aligned")

    if np.isfinite(rs_5d) and abs(rs_5d) >= MATERIAL_RS_5D:
        score += 0.20
        reasons.append(f"material 5d RS vs SPY ({rs_5d * 100:+.1f}%)")
    else:
        reasons.append("5d RS small — may be chop, not capital shift")

    # Absolute + relative same sign → real money move, not just "lost less"
    if np.isfinite(ret_5d) and np.isfinite(rs_5d) and _sign(ret_5d) == want and _sign(rs_5d) == want:
        score += 0.15
        reasons.append("absolute and relative both confirm")
    elif np.isfinite(ret_5d) and _sign(ret_5d) != want and _sign(rs_5d) == want:
        score += 0.05
        reasons.append("only relative (sector falling less / rising less) — weaker signal")

    if np.isfinite(ret_1d) and abs(ret_1d) >= MATERIAL_RET_1D and _sign(ret_1d) == want:
        score += 0.08
        reasons.append("day move material and aligned")

    if np.isfinite(rvol) and rvol >= RVOL_CONFIRM:
        score += 0.12
        reasons.append(f"volume confirms (rvol {rvol:.2f}x)")
    elif np.isfinite(rvol) and rvol < 0.85:
        score -= 0.05
        reasons.append(f"light volume (rvol {rvol:.2f}x) — less definitive")

    if above is True and want == 1:
        score += 0.05
        reasons.append("price above 20d MA (structure supports inflow)")
    elif above is False and want == -1:
        score += 0.05
        reasons.append("price below 20d MA (structure supports outflow)")
    elif above is True and want == -1:
        reasons.append("still above 20d MA while outflowing — may be rotation, not collapse")
    elif above is False and want == 1:
        reasons.append("below 20d MA while inflowing — repair, not established leadership")

    score = float(max(0.0, min(1.0, score)))
    return score, score >= DEFINITIVE_SCORE_CUT, reasons


def classify_direction(
    flow: float,
    *,
    rs_1d: float = float("nan"),
    rs_5d: float = float("nan"),
    day_mode: bool = True,
) -> str:
    """Classify in/out. day_mode uses 1d RS + day-weighted flow (for *today*)."""
    if not np.isfinite(flow) and not np.isfinite(rs_1d) and not np.isfinite(rs_5d):
        return "neutral"

    if day_mode:
        # Today: 1d RS is the primary map (catches SOXX dump even if 5d still green)
        if np.isfinite(rs_1d) and abs(rs_1d) >= MATERIAL_RS_1D:
            return "in" if rs_1d > 0 else "out"
        # Tie-break: day-weighted flow when RS1d is noise-small
        if np.isfinite(flow):
            if flow >= 0.0012:
                return "in"
            if flow <= -0.0012:
                return "out"
        if np.isfinite(rs_1d) and abs(rs_1d) > 1e-6:
            return "in" if rs_1d > 0 else "out"
        return "neutral"

    # Multi-day leadership
    if np.isfinite(rs_5d) and abs(rs_5d) >= MATERIAL_RS_5D * 0.5:
        return "in" if rs_5d > 0 else "out"
    if not np.isfinite(flow):
        return "neutral"
    if abs(flow) < 0.0015:
        return "neutral"
    return "in" if flow > 0 else "out"


def score_sectors(
    panel: Mapping[str, pd.DataFrame],
    benchmark: str = "SPY",
    sector_meta: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[SectorFlow]:
    """Score each sector/theme ETF in meta that exists in panel.

    Primary rank = day-weighted flow (where money moved *today*).
    """
    meta = sector_meta or SECTOR_META
    if benchmark not in panel:
        return []
    bench = panel[benchmark]["close"].astype(float)

    rows: list[SectorFlow] = []
    for etf, info in meta.items():
        if etf not in panel:
            continue
        # Don't double-count QQQ as both bench helper and sector if bench is QQQ
        if etf == benchmark:
            continue
        df = panel[etf]
        close = df["close"].astype(float)
        vol = df["volume"] if "volume" in df.columns else pd.Series(dtype=float)

        r1 = ret_n(close, 1)
        r5 = ret_n(close, 5)
        r21 = ret_n(close, 21)
        rs1 = rs_n(close, bench, 1)
        rs5 = rs_n(close, bench, 5)
        rs21 = rs_n(close, bench, 21)
        ama = above_ma(close, 20)
        rv = rvol_last(vol, 20) if len(vol) else float("nan")
        day_fs = flow_score(rs1, rs5, rs21, r1, ama)
        week_fs = week_flow_score(rs1, rs5, rs21, ama)
        day_dir = classify_direction(day_fs, rs_1d=rs1, rs_5d=rs5, day_mode=True)
        week_dir = classify_direction(week_fs, rs_1d=rs1, rs_5d=rs5, day_mode=False)
        dscore, dflag, dreasons = definitive_assessment(
            rs_1d=rs1,
            rs_5d=rs5,
            rs_21d=rs21,
            ret_1d=r1,
            ret_5d=r5,
            above=ama,
            rvol=rv,
            direction=day_dir,
        )
        # Day-only note when week disagrees
        if day_dir != "neutral" and week_dir != "neutral" and day_dir != week_dir:
            dreasons = list(dreasons) + [
                f"day {day_dir} vs week {week_dir} — treat as session rotation, not regime flip"
            ]
            dscore = float(max(0.0, dscore - 0.12))
            dflag = dscore >= DEFINITIVE_SCORE_CUT

        rows.append(
            SectorFlow(
                etf=etf,
                name=str(info.get("name", etf)),
                bucket=str(info.get("bucket", "other")),
                ret_1d=r1,
                ret_5d=r5,
                ret_21d=r21,
                rs_1d=rs1,
                rs_5d=rs5,
                rs_21d=rs21,
                flow_score=day_fs,
                week_flow_score=week_fs,
                day_direction=day_dir,
                flow_direction=day_dir,
                week_direction=week_dir,
                definitive=dflag,
                definitive_score=dscore,
                definitive_reasons=dreasons,
                above_ma20=ama,
                rvol=rv,
                focus_names=list(info.get("names") or []),
                theme=bool(info.get("theme", False)),
            )
        )

    rows.sort(key=lambda r: (r.flow_score if np.isfinite(r.flow_score) else -9.0), reverse=True)
    for i, r in enumerate(rows, 1):
        r.rank = i
    return rows


def _ratio_ret(panel: Mapping[str, pd.DataFrame], a: str, b: str, n: int) -> float:
    if a not in panel or b not in panel:
        return float("nan")
    joined = pd.concat(
        [panel[a]["close"].rename("a"), panel[b]["close"].rename("b")],
        axis=1,
    ).dropna()
    if len(joined) < n + 1:
        return float("nan")
    ratio = joined["a"] / joined["b"].replace(0, np.nan)
    return ret_n(ratio, n)


def market_context(panel: Mapping[str, pd.DataFrame], benchmark: str = "SPY") -> dict[str, Any]:
    ctx: dict[str, Any] = {"benchmark": benchmark}
    if benchmark in panel:
        c = panel[benchmark]["close"]
        ctx["spy_ret_1d"] = ret_n(c, 1)
        ctx["spy_ret_5d"] = ret_n(c, 5)
        ctx["spy_ret_21d"] = ret_n(c, 21)
        ctx["spy_above_ma20"] = above_ma(c, 20)
    if "QQQ" in panel and benchmark in panel and benchmark != "QQQ":
        ctx["qqq_ret_1d"] = ret_n(panel["QQQ"]["close"], 1)
        ctx["qqq_ret_5d"] = ret_n(panel["QQQ"]["close"], 5)
        ctx["qqq_spy_rs_1d"] = rs_n(panel["QQQ"]["close"], panel[benchmark]["close"], 1)
        ctx["qqq_spy_rs_5d"] = rs_n(panel["QQQ"]["close"], panel[benchmark]["close"], 5)
    for etf in ("SOXX", "SMH", "XLK", "IGV"):
        if etf in panel and benchmark in panel:
            ctx[f"{etf.lower()}_ret_1d"] = ret_n(panel[etf]["close"], 1)
            ctx[f"{etf.lower()}_rs_1d"] = rs_n(panel[etf]["close"], panel[benchmark]["close"], 1)

    ratios = {}
    for a, b, label in RATIO_PAIRS:
        ratios[label] = {
            "pair": f"{a}/{b}",
            "ret_1d": _ratio_ret(panel, a, b, 1),
            "ret_5d": _ratio_ret(panel, a, b, 5),
            "ret_21d": _ratio_ret(panel, a, b, 21),
        }
    ctx["ratios"] = ratios
    return ctx


def _bucket_dirs(sectors: Sequence[SectorFlow], bucket: str) -> tuple[list[SectorFlow], list[SectorFlow]]:
    ins = [s for s in sectors if s.bucket == bucket and s.flow_direction == "in"]
    outs = [s for s in sectors if s.bucket == bucket and s.flow_direction == "out"]
    return ins, outs


def detect_theme_rotations(
    sectors: Sequence[SectorFlow],
    ctx: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Named intra-market rotations (semis→tech, etc.)."""
    by = {s.etf: s for s in sectors}
    ratios = ctx.get("ratios") or {}
    out: list[dict[str, Any]] = []

    soxx = by.get("SOXX") or by.get("SMH")
    xlk = by.get("XLK")
    igv = by.get("IGV")
    semis_vs_tech = (ratios.get("semis_vs_tech") or {}).get("ret_1d", float("nan"))
    if soxx is None and "semis_vs_tech" in ratios:
        semis_vs_tech = ratios["semis_vs_tech"].get("ret_1d", float("nan"))

    # Case: money left semis relative to tech complex (desk: SOXX dump, capital in tech sleeve)
    if soxx is not None:
        # Prefer the best day-in tech-ish book as the "to" sleeve (XLC often leads when XLK mixed)
        candidates = [s for s in (xlk, igv, by.get("XLC"), by.get("QQQ")) if s is not None]
        tech_side = None
        if candidates:
            tech_side = max(
                candidates,
                key=lambda s: s.rs_1d if np.isfinite(s.rs_1d) else -9.0,
            )
        soxx_out = soxx.flow_direction == "out" or (
            np.isfinite(soxx.rs_1d) and soxx.rs_1d < -MATERIAL_RS_1D
        )
        ratio_confirms = np.isfinite(semis_vs_tech) and semis_vs_tech < -MATERIAL_RS_1D
        relative_underperform = (
            tech_side is not None
            and np.isfinite(soxx.rs_1d)
            and np.isfinite(tech_side.rs_1d)
            and soxx.rs_1d < tech_side.rs_1d - MATERIAL_RS_1D
        )
        if soxx_out and (ratio_confirms or relative_underperform) and tech_side is not None:
            mag = (
                abs(float(semis_vs_tech))
                if np.isfinite(semis_vs_tech)
                else abs(soxx.rs_1d - (tech_side.rs_1d or 0))
            )
            abs_tech_in = tech_side.flow_direction == "in" or (
                np.isfinite(tech_side.rs_1d) and tech_side.rs_1d > 0
            )
            if abs_tech_in:
                summary = (
                    f"Money left {soxx.name} ({soxx.etf} day {soxx.ret_1d * 100:+.1f}% / "
                    f"RS1d={soxx.rs_1d * 100:+.2f}%) and rotated toward {tech_side.name} "
                    f"({tech_side.etf} RS1d={tech_side.rs_1d * 100:+.2f}%)."
                )
            else:
                summary = (
                    f"{soxx.name} underperformed the tech complex today "
                    f"({soxx.etf} RS1d={soxx.rs_1d * 100:+.2f}% vs {tech_side.etf} "
                    f"RS1d={tech_side.rs_1d * 100:+.2f}%) — chips are the weak sleeve even if broad tech is mixed."
                )
            if np.isfinite(semis_vs_tech):
                summary += f" SOXX/XLK day ratio {semis_vs_tech * 100:+.2f}%."
            out.append(
                {
                    "id": "semis_to_tech",
                    "label": "Semis → Tech",
                    "from_etf": soxx.etf,
                    "to_etf": tech_side.etf,
                    "summary": summary,
                    "magnitude": mag if np.isfinite(mag) else None,
                    "definitive": bool(
                        soxx.flow_direction == "out"
                        and (tech_side.flow_direction == "in" or ratio_confirms)
                        and (ratio_confirms or relative_underperform)
                    ),
                }
            )

    # Reverse: semis bid vs tech lag
    if soxx is not None and xlk is not None:
        if soxx.flow_direction == "in" and xlk.flow_direction == "out":
            out.append(
                {
                    "id": "tech_to_semis",
                    "label": "Tech → Semis",
                    "from_etf": xlk.etf,
                    "to_etf": soxx.etf,
                    "summary": (
                        f"Semis leading tech today ({soxx.etf} in, {xlk.etf} out) — "
                        "chip complex is the high-RS sleeve."
                    ),
                    "magnitude": abs((soxx.rs_1d or 0) - (xlk.rs_1d or 0)),
                    "definitive": bool(soxx.definitive or xlk.definitive),
                }
            )

    # Software vs broad tech
    if igv is not None and xlk is not None:
        if igv.flow_direction == "in" and xlk.flow_direction == "out":
            out.append(
                {
                    "id": "tech_to_software",
                    "label": "Tech → Software",
                    "from_etf": "XLK",
                    "to_etf": "IGV",
                    "summary": "Software (IGV) bid while broad tech lags — prefer software names over chip-heavy XLK.",
                    "magnitude": abs((igv.rs_1d or 0) - (xlk.rs_1d or 0)),
                    "definitive": False,
                }
            )

    return out


def classify_rotation(
    sectors: Sequence[SectorFlow],
    ctx: Mapping[str, Any],
) -> dict[str, Any]:
    """Market-level rotation narrative + definitiveness (day-primary)."""
    ins = [s for s in sectors if s.flow_direction == "in"]
    outs = sorted(
        [s for s in sectors if s.flow_direction == "out"],
        key=lambda s: s.flow_score if np.isfinite(s.flow_score) else 9.0,
    )
    def_in = [s for s in ins if s.bucket == "defensive"]
    growth_buckets = {"growth", "tech", "software", "semis"}
    growth_in = [s for s in ins if s.bucket in growth_buckets]
    def_out = [s for s in outs if s.bucket == "defensive"]
    growth_out = [s for s in outs if s.bucket in growth_buckets]
    semis_in, semis_out = _bucket_dirs(sectors, "semis")
    tech_in, tech_out = _bucket_dirs(sectors, "tech")
    software_in, _ = _bucket_dirs(sectors, "software")

    ratios = ctx.get("ratios") or {}
    xly_xlp = ratios.get("discretionary_vs_staples", {}).get("ret_5d", float("nan"))
    xlk_xlp = ratios.get("tech_vs_staples", {}).get("ret_5d", float("nan"))
    semis_tech_1d = ratios.get("semis_vs_tech", {}).get("ret_1d", float("nan"))
    spy_1 = ctx.get("spy_ret_1d", float("nan"))
    spy_5 = ctx.get("spy_ret_5d", float("nan"))

    themes = detect_theme_rotations(sectors, ctx)
    kind = "unclear"
    summary_parts: list[str] = []

    # Highest-priority: named theme rotation (semis ↔ tech)
    theme_ids = {t["id"] for t in themes}
    if "semis_to_tech" in theme_ids:
        kind = "semis_to_tech"
        t = next(x for x in themes if x["id"] == "semis_to_tech")
        summary_parts.append(t["summary"])
    elif "tech_to_semis" in theme_ids:
        kind = "tech_to_semis"
        t = next(x for x in themes if x["id"] == "tech_to_semis")
        summary_parts.append(t["summary"])
    elif np.isfinite(spy_1) and spy_1 < -0.01 and len(outs) >= max(3, len(sectors) // 2):
        kind = "broad_risk_off"
        summary_parts.append("Broad risk-off session: SPY soft and many books leaking vs market.")
    elif np.isfinite(spy_5) and spy_5 < -0.015 and len(outs) >= max(3, len(sectors) // 2):
        kind = "broad_risk_off"
        summary_parts.append("Broad risk-off: SPY soft on the week and many sectors leaking vs market.")
    elif len(def_in) >= 2 and len(growth_out) >= 2:
        kind = "defensive"
        summary_parts.append(
            "Defensive rotation: staples/health/utilities attracting relative bids; growth lagging."
        )
    elif (semis_out or tech_out) and (tech_in or software_in or semis_in) and ins and outs:
        kind = "internal"
        summary_parts.append(
            "Internal growth rotation: capital moving *inside* risk assets "
            f"(semis out={','.join(s.etf for s in semis_out) or '—'}; "
            f"tech/software in={','.join(s.etf for s in tech_in + software_in) or '—'})."
        )
    elif len(growth_in) >= 1 and len(def_out) >= 1 and (
        (np.isfinite(xly_xlp) and xly_xlp > 0) or (np.isfinite(xlk_xlp) and xlk_xlp > 0)
    ):
        kind = "risk_on"
        lead_names = ", ".join(s.name for s in growth_in[:3]) or "growth books"
        summary_parts.append(
            f"Risk-on tilt: {lead_names} leading defensives — capital prefers beta."
        )
    elif ins and outs:
        kind = "internal"
        summary_parts.append(
            "Internal rotation: money moving *between* sector/theme books — not a clean exit from equities."
        )
    elif ins and not outs:
        kind = "broad_bid"
        summary_parts.append("Broad sector bid vs SPY — leadership is wide, not concentrated.")
    else:
        summary_parts.append("No clean leadership cluster — wait for multi-day RS agreement.")

    top_in = ins[:4]
    top_out = outs[:4]
    if top_in or top_out:
        avg_d = float(
            np.nanmean(
                [s.definitive_score for s in list(top_in) + list(top_out) if np.isfinite(s.definitive_score)]
                or [0.0]
            )
        )
    else:
        avg_d = 0.0

    ratio_agree = 0
    if kind in ("risk_on", "semis_to_tech", "tech_to_semis", "internal"):
        if np.isfinite(semis_tech_1d) and abs(semis_tech_1d) >= MATERIAL_RS_1D:
            ratio_agree += 1
        if np.isfinite(xlk_xlp) and abs(xlk_xlp) > 0:
            ratio_agree += 1
    if kind == "defensive":
        if np.isfinite(xly_xlp) and xly_xlp < 0:
            ratio_agree += 1
        if np.isfinite(xlk_xlp) and xlk_xlp < 0:
            ratio_agree += 1

    theme_boost = 0.2 if kind in ("semis_to_tech", "tech_to_semis") else 0.0
    conf = float(
        max(
            0.0,
            min(
                1.0,
                0.50 * avg_d
                + 0.12 * ratio_agree
                + theme_boost
                + (0.12 if kind not in ("unclear",) else 0.0),
            ),
        )
    )
    is_def = conf >= 0.55 and kind not in ("unclear",) and (bool(top_in) or bool(top_out))
    # Named theme with both sides confirming day direction is definitive enough for desk
    if kind == "semis_to_tech" and any(t.get("definitive") for t in themes):
        is_def = True
        conf = max(conf, 0.62)

    if top_in:
        summary_parts.append(
            "Money in today: " + ", ".join(f"{s.name}({s.etf} {s.rs_1d * 100:+.1f}%)" for s in top_in[:4])
        )
    if top_out:
        summary_parts.append(
            "Money out today: " + ", ".join(f"{s.name}({s.etf} {s.rs_1d * 100:+.1f}%)" for s in top_out[:4])
        )
    if not is_def:
        summary_parts.append(
            "Not fully definitive — confirm with volume / multi-day before size-up."
        )
    else:
        summary_parts.append("Day rotation prints with enough confirmation for a desk read.")

    return {
        "kind": kind,
        "summary": " ".join(summary_parts),
        "is_definitive": is_def,
        "confidence": round(conf, 3),
        "money_in_etfs": [s.etf for s in top_in],
        "money_out_etfs": [s.etf for s in top_out],
        "xly_xlp_5d": xly_xlp if np.isfinite(xly_xlp) else None,
        "xlk_xlp_5d": xlk_xlp if np.isfinite(xlk_xlp) else None,
        "semis_vs_tech_1d": semis_tech_1d if np.isfinite(semis_tech_1d) else None,
        "theme_rotations": themes,
    }


def trading_notes(
    rotation: Mapping[str, Any],
    sectors: Sequence[SectorFlow],
    ctx: Mapping[str, Any],
) -> list[str]:
    """Operator checklist — what to keep in mind when trading the scan."""
    notes: list[str] = []
    kind = rotation.get("kind")
    is_def = bool(rotation.get("is_definitive"))
    by = {s.etf: s for s in sectors}

    notes.append(
        "Play relative strength: prefer longs in *today's* leaders, not knife-catches in books that just leaked."
    )
    notes.append(
        "Index → theme/sector → stock: if SOXX is leaking, chip names fight the tape even if XLK is green."
    )

    if kind == "semis_to_tech":
        notes.append(
            "Semis → tech today: de-risk pure chip exposure (SOXX/SMH names); prefer software / mega-cap tech "
            "that is leading on the day — do not average down semis just because 'tech is up'."
        )
        notes.append(
            "XLK can print green while SOXX is red (XLK is mixed). Trade the *sleeve* (SOXX vs IGV/software), not the label."
        )
    elif kind == "tech_to_semis":
        notes.append(
            "Tech → semis: high-RS is the chip complex — favor SOXX/SMH leaders over soft software if structure holds."
        )
    elif kind == "defensive":
        notes.append(
            "Defensive rotation (XLP/XLV/XLU): growth-style traders often stand aside / reduce beta — "
            "staples don't always pay enough for the same risk."
        )
        notes.append("Do not confuse defensive bid with 'crash' — money can stay in equities and just hide.")
    elif kind == "risk_on":
        notes.append(
            "Risk-on: favor high-RS growth/discretionary/tech names; fade late-chasing of beaten defensives."
        )
    elif kind == "broad_risk_off":
        notes.append(
            "Broad risk-off: prioritize capital preservation; new swing longs need structure reclaim (e.g. key MAs)."
        )
    elif kind == "internal":
        notes.append(
            "Internal rotation: stay long the *new* leaders; don't sell the whole market because one sleeve dies."
        )

    if not is_def:
        notes.append(
            "Not definitive: wait for multi-horizon agreement and/or volume confirmation before size-up."
        )
    else:
        notes.append(
            "Confirmed day rotation: still use stops behind structure — flow is a map, not an entry trigger."
        )

    soxx = by.get("SOXX") or by.get("SMH")
    xlk = by.get("XLK")
    if soxx and soxx.flow_direction == "out":
        notes.append(
            f"{soxx.etf} day outflow (RS1d {soxx.rs_1d * 100:+.2f}%): "
            "treat semis as the weak sleeve until SOXX reclaims day RS."
        )
    if xlk and xlk.flow_direction == "in" and soxx and soxx.flow_direction == "out":
        notes.append(
            "Tech bid + semis dump = classic internal rotation. Hunt strength *inside* tech, not broken chip charts."
        )
    if xlk and xlk.flow_direction == "out" and xlk.above_ma20 is False:
        notes.append(
            "Tech (XLK) weak + below MA20: treat Nasdaq/high-beta risk carefully — growth leadership is cracked."
        )

    spy_5 = ctx.get("spy_ret_5d")
    if spy_5 is not None and np.isfinite(spy_5) and spy_5 < -0.02:
        notes.append("SPY soft over 5d: lower size; require cleaner sector + name alignment.")

    notes.append(
        "Day money ≠ multi-week thesis: a one-day rip on light volume often fails; re-check after the close."
    )
    notes.append(
        "OHLCV relative strength is a proxy — not dark-pool tickets. Themes (SOXX/IGV) must be loaded or the map lies."
    )
    return notes


# ---------------------------------------------------------------------------
# Build report
# ---------------------------------------------------------------------------


def build_report(
    panel: Mapping[str, pd.DataFrame],
    *,
    benchmark: str = "SPY",
    source_used: str = "unknown",
    sector_meta: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Full money-flow report from an OHLCV panel."""
    if benchmark not in panel:
        return {
            "ok": False,
            "error": f"benchmark {benchmark} missing from panel",
            "disclaimer": DISCLAIMER,
        }

    sectors = score_sectors(panel, benchmark=benchmark, sector_meta=sector_meta)
    if not sectors:
        return {
            "ok": False,
            "error": "no sector ETFs scored (check data)",
            "disclaimer": DISCLAIMER,
        }

    ctx = market_context(panel, benchmark=benchmark)
    rotation = classify_rotation(sectors, ctx)
    money_in = [s.to_dict() for s in sectors if s.flow_direction == "in"][:6]
    money_out = [
        s.to_dict()
        for s in sorted(
            [s for s in sectors if s.flow_direction == "out"],
            key=lambda x: x.flow_score if np.isfinite(x.flow_score) else 9.0,
        )[:6]
    ]
    notes = trading_notes(rotation, sectors, ctx)
    # Prefer focus names from *day* leaders, not week
    themes = rotation.get("theme_rotations") or []

    # as-of from benchmark last bar
    asof_bar = None
    try:
        asof_bar = str(pd.Timestamp(panel[benchmark].index[-1]).date())
    except Exception:  # noqa: BLE001
        asof_bar = None

    # Desk-compatible leaders/laggards (matches sector_watchlist shape)
    leaders = [s.to_dict() for s in sectors[:4]]
    laggards = [s.to_dict() for s in list(reversed(sectors[-3:]))] if len(sectors) >= 3 else []

    narrative = [
        rotation.get("summary") or "",
        f"Regime kind={rotation.get('kind')} definitive={rotation.get('is_definitive')} "
        f"conf={rotation.get('confidence')}",
    ]
    if money_in:
        narrative.append(
            "Leaders: "
            + ", ".join(f"{r['etf']} RS5={((r.get('rs_5d') or 0)*100):+.1f}%" for r in money_in[:3])
        )
    if money_out:
        narrative.append(
            "Outflows: "
            + ", ".join(f"{r['etf']} RS5={((r.get('rs_5d') or 0)*100):+.1f}%" for r in money_out[:3])
        )

    return {
        "ok": True,
        "asof": datetime.now(timezone.utc).isoformat(),
        "asof_bar": asof_bar,
        "benchmark": benchmark,
        "source": source_used,
        "lookbacks_days": list(LOOKBACKS),
        "market_context": _json_safe(ctx),
        "rotation": _json_safe(rotation),
        "theme_rotations": _json_safe(themes),
        "sectors_ranked": [s.to_dict() for s in sectors],
        "money_in": money_in,
        "money_out": money_out,
        "leaders": leaders,
        "laggards": laggards,
        "trading_notes": notes,
        "narrative": [n for n in narrative if n],
        "disclaimer": DISCLAIMER,
        # aliases for existing SectorBlock UI
        "watch_names": _watch_names_from_leaders(sectors),
        "missing_themes": [
            t for t in THEME_FETCH_ALWAYS if t not in {s.etf for s in sectors}
        ],
    }


def _watch_names_from_leaders(sectors: Sequence[SectorFlow], limit: int = 20) -> list[dict[str, Any]]:
    """Expand focus names from top inflow sectors for desk watchlist."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    ordered = [s for s in sectors if s.flow_direction == "in"] + list(sectors)
    for s in ordered:
        for n in s.focus_names:
            if n in seen:
                continue
            seen.add(n)
            rows.append(
                {
                    "symbol": n,
                    "sector_hint": s.name,
                    "etf": s.etf,
                    "score": s.flow_score if np.isfinite(s.flow_score) else None,
                    "rs_5d": s.rs_5d if np.isfinite(s.rs_5d) else None,
                    "rs_21d": s.rs_21d if np.isfinite(s.rs_21d) else None,
                    "parent_definitive": s.definitive,
                }
            )
            if len(rows) >= limit:
                return rows
    return rows


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, float):
        if not np.isfinite(obj):
            return None
        return obj
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if not np.isfinite(v) else v
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


def run_scan(
    *,
    source: str = "auto",
    period: str = "6mo",
    cache_dir: Path = CACHE_1D,
    benchmark: str = "SPY",
) -> dict[str, Any]:
    symbols = list(SECTOR_META.keys()) + [benchmark]
    panel = load_panel(symbols, source=source, cache_dir=cache_dir, period=period)
    used = source
    if source in ("auto", "local"):
        theme_hits = sum(1 for t in THEME_FETCH_ALWAYS if t in panel)
        local_spdr = sum(
            1
            for s, meta in SECTOR_META.items()
            if not meta.get("theme") and s in panel and (cache_dir / f"{s}.parquet").exists()
        )
        if theme_hits >= 2 and local_spdr >= 6:
            used = "mixed" if source != "local" or theme_hits else "local"
        elif theme_hits >= 2:
            used = "mixed"
        elif local_spdr >= 6:
            used = "local_incomplete"  # SPDR only — semis map missing
        else:
            used = "mixed"
    return build_report(panel, benchmark=benchmark, source_used=used)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _pct(x: float | None, digits: int = 1) -> str:
    if x is None or not np.isfinite(x):
        return "   —  "
    return f"{x * 100:+{digits + 4}.{digits}f}%"


def print_human(report: dict[str, Any]) -> None:
    if not report.get("ok"):
        print("ERROR:", report.get("error"))
        print(report.get("disclaimer", ""))
        return

    rot = report.get("rotation") or {}
    ctx = report.get("market_context") or {}
    print("=" * 78)
    print("  SECTOR MONEY FLOW  — where capital is rotating")
    print("=" * 78)
    print(f"  asof bar: {report.get('asof_bar')}   source: {report.get('source')}   bench: {report.get('benchmark')}")
    print(
        f"  SPY 1d {_pct(ctx.get('spy_ret_1d'))}  5d {_pct(ctx.get('spy_ret_5d'))}  21d {_pct(ctx.get('spy_ret_21d'))}"
    )
    print()
    print(
        f"  ROTATION: {str(rot.get('kind', '?')).upper()}  "
        f"definitive={'YES' if rot.get('is_definitive') else 'NO'}  "
        f"conf={rot.get('confidence')}"
    )
    print(f"  {rot.get('summary', '')}")
    if rot.get("semis_vs_tech_1d") is not None:
        print(f"  SOXX/XLK day ratio: {_pct(rot.get('semis_vs_tech_1d'))}")
    themes = report.get("theme_rotations") or rot.get("theme_rotations") or []
    for t in themes:
        print(f"  THEME: {t.get('label')}: {t.get('summary')}")
    miss = report.get("missing_themes") or []
    if miss:
        print(f"  WARNING missing themes (map incomplete): {', '.join(miss)}")
    print()
    print(
        f"  {'#':<3} {'ETF':<5} {'sector':<16} {'day':<4} {'wk':<4} "
        f"{'1d':>7} {'RS1d':>7} {'5d':>7} {'RS5':>7} {'def':>5} {'rvol':>5}"
    )
    print("  " + "-" * 86)
    for s in report.get("sectors_ranked") or []:
        dflag = "YES" if s.get("definitive") else "no"
        rv = s.get("rvol")
        rv_s = f"{rv:.2f}" if isinstance(rv, (int, float)) and np.isfinite(rv) else "  — "
        print(
            f"  {s.get('rank', '?'):<3} {s.get('etf', ''):<5} {str(s.get('name', '')):<16} "
            f"{(s.get('day_direction') or s.get('flow_direction') or '?'):<4} "
            f"{(s.get('week_direction') or '?'):<4} "
            f"{_pct(s.get('ret_1d'))} {_pct(s.get('rs_1d'))} "
            f"{_pct(s.get('ret_5d'))} {_pct(s.get('rs_5d'))} "
            f"{dflag:>5} {rv_s:>5}"
        )

    print()
    print("  MONEY IN (leaders)")
    for s in report.get("money_in") or []:
        print(
            f"    → {s['etf']} {s['name']:<12} flow={s.get('flow_score')}  "
            f"def={s.get('definitive_score')}  "
            f"{'; '.join((s.get('definitive_reasons') or [])[:2])}"
        )
    print("  MONEY OUT (rotating away)")
    for s in report.get("money_out") or []:
        print(
            f"    ← {s['etf']} {s['name']:<12} flow={s.get('flow_score')}  "
            f"def={s.get('definitive_score')}  "
            f"{'; '.join((s.get('definitive_reasons') or [])[:2])}"
        )

    print()
    print("  KEEP IN MIND WHEN TRADING")
    for i, n in enumerate(report.get("trading_notes") or [], 1):
        print(f"  {i}. {n}")
    print()
    print(" ", report.get("disclaimer"))


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Sector money-flow / rotation scanner")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--source", choices=("auto", "local", "yfinance"), default="auto")
    ap.add_argument("--period", default="6mo", help="yfinance period when needed")
    ap.add_argument("--benchmark", default="SPY")
    args = ap.parse_args(list(argv) if argv is not None else None)

    report = run_scan(source=args.source, period=args.period, benchmark=args.benchmark)
    if args.json:
        print(json.dumps(_json_safe(report), indent=2, default=str))
    else:
        print_human(report)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
