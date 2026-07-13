"""Build the causal daily regime parquet used by regime_gate.py and direction reports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = ROOT / "models" / "_shared" / "REGIME_SPEC.json"
CACHE_DIR = ROOT / "data_cache" / "1d"
DEFAULT_OUT = ROOT / "models" / "_shared" / "regime" / "regime_daily.parquet"


def _load_price(symbol: str) -> pd.Series | None:
    """Load close series from 1d cache, tolerant to .US suffix and leading ^."""
    candidates = {symbol, symbol.lstrip("^"), f"{symbol}.US", f"{symbol.lstrip('^')}.US"}
    for name in candidates:
        p = CACHE_DIR / f"{name}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            if "close" in df.columns:
                return df["close"].sort_index().astype(float)
    return None


def _trend_component(close: pd.Series) -> pd.Series:
    """Return value in [-1,1] based on 20/50 SMA position."""
    sma20 = close.rolling(20, min_periods=15).mean()
    sma50 = close.rolling(50, min_periods=35).mean()
    s1 = np.where(close > sma20, 1.0, -1.0)
    s2 = np.where(close > sma50, 1.0, -1.0)
    return pd.Series(0.5 * (s1 + s2), index=close.index)


def _ratio_trend(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Trend of ratio vs its 20/50 SMA, in [-1,1]."""
    ratio = numerator / denominator.replace(0, np.nan)
    sma20 = ratio.rolling(20, min_periods=15).mean()
    sma50 = ratio.rolling(50, min_periods=35).mean()
    s1 = np.where(ratio > sma20, 1.0, -1.0)
    s2 = np.where(ratio > sma50, 1.0, -1.0)
    return pd.Series(0.5 * (s1 + s2), index=ratio.index)


def build_regime(start: str, end: str | None, out: Path) -> Path:
    """Build the regime parquet and return its path."""
    if not CACHE_DIR.exists():
        raise FileNotFoundError(f"1d cache not found: {CACHE_DIR}")

    spec = json.loads(SPEC_PATH.read_text()) if SPEC_PATH.exists() else {}
    inputs = spec.get("build", {}).get("inputs", {})
    thresholds = spec.get("thresholds", {"risk_on": 0.30, "risk_off": -0.30})
    sectors = inputs.get("sectors", [])

    def get(sym: str):
        s = _load_price(sym)
        if s is None:
            raise FileNotFoundError(f"no 1d price for {sym}")
        return s

    # Index trend
    idx_parts = []
    for sym in inputs.get("index", ["SPY", "QQQ"]):
        idx_parts.append(_trend_component(get(sym)))
    comp_index_trend = pd.concat(idx_parts, axis=1).mean(axis=1)

    # Defensive vs SPY
    spy = get("SPY")
    def_parts = []
    for sym in inputs.get("defensive", ["XLP", "HYG", "LQD"]):
        def_parts.append(_ratio_trend(get(sym), spy))
    comp_defensive = pd.concat(def_parts, axis=1).mean(axis=1)

    # VIX inverse
    vix = get("^VIX")
    vix_sma20 = vix.rolling(20, min_periods=15).mean()
    vix_sma50 = vix.rolling(50, min_periods=35).mean()
    comp_vix = -0.5 * (
        np.where(vix > vix_sma20, 1.0, -1.0)
        + np.where(vix > vix_sma50, 1.0, -1.0)
    )
    comp_vix = pd.Series(comp_vix, index=vix.index)

    # Rates
    tnx = get("^TNX")
    tnx_sma20 = tnx.rolling(20, min_periods=15).mean()
    tnx_sma50 = tnx.rolling(50, min_periods=35).mean()
    comp_rates = -0.5 * (
        np.where(tnx > tnx_sma20, 1.0, -1.0)
        + np.where(tnx > tnx_sma50, 1.0, -1.0)
    )
    comp_rates = pd.Series(comp_rates, index=tnx.index)

    # Credit (HYG / LQD)
    hyg = get("HYG")
    lqd = get("LQD")
    comp_credit = _ratio_trend(hyg, lqd)

    score = (
        0.25 * comp_index_trend
        + 0.20 * comp_defensive
        + 0.25 * comp_vix
        + 0.10 * comp_rates
        + 0.20 * comp_credit
    )

    def _label(v: float) -> str:
        if v >= thresholds.get("risk_on", 0.30):
            return "risk_on"
        if v <= thresholds.get("risk_off", -0.30):
            return "risk_off"
        return "neutral"

    df = pd.DataFrame(
        {
            "score": score,
            "label": pd.Series(score, index=score.index).map(_label),
            "comp_index_trend": comp_index_trend,
            "comp_defensive": comp_defensive,
            "comp_vix": comp_vix,
            "comp_rates": comp_rates,
            "comp_credit": comp_credit,
        },
        index=score.index,
    )

    for sym in sectors:
        close = get(sym)
        sma20 = close.rolling(20, min_periods=15).mean()
        sma50 = close.rolling(50, min_periods=35).mean()
        df[f"sector_ok_{sym}.US"] = (close > sma20) & (close > sma50)

    # Slice to requested range
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end) if end else df.index.max()
    df = df[(df.index >= start_ts) & (df.index <= end_ts)]

    out.parent.mkdir(parents=True, exist_ok=True)
    df.index.name = "date"
    df.to_parquet(out)
    return out


def main():
    parser = argparse.ArgumentParser(description="Build causal daily regime parquet")
    parser.add_argument("build")
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    if args.build != "build":
        parser.error("only 'build' subcommand is supported")
    out = build_regime(args.start, args.end, args.out)
    print(out)


if __name__ == "__main__":
    main()
