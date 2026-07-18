#!/usr/bin/env python3
"""EMA/VWAP/Volume + synthetic gamma-wall backtest.

Interprets the request as:
- EMA 9 / 21 / 50 stack: only trade when aligned (bull stack for long, bear stack for short).
- Price above the fast EMA and VWAP for long; below for short.
- Volume above its 20-bar average confirms the move.
- Synthetic call/put walls avoid entries that are pushing into gamma resistance.
- Backtest with ATR-based stops and report equity/wr/dd.

Run:
    python models/poc_va_gex/research/ema_vwap_volume_gex_backtest.py SPY --interval 1h --period 2y
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.signal import argrelextrema

pd.set_option("future.no_silent_downcasting", True)

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "models" / "poc_va_gex" / "artifacts"
OUT.mkdir(parents=True, exist_ok=True)


@dataclass
class BacktestResult:
    symbol: str
    interval: str
    period: str
    n_trades: int
    win_rate: float
    final: float
    total_ret: float
    max_dd: float
    avg_trade: float
    best: float
    worst: float
    avg_hold_bars: float
    longs: int
    shorts: int
    long_pnl: float
    short_pnl: float


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev = close.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(span=n, adjust=False).mean()


def compute_vwap(df: pd.DataFrame, interval: str) -> pd.Series:
    """Session-anchored VWAP for intraday bars; rolling VWAP for daily/weekly."""
    hlc3 = (df["high"] + df["low"] + df["close"]) / 3.0
    if interval.endswith(("m", "h")):
        tmp = df.copy()
        tmp["date"] = pd.to_datetime(tmp.index).date
        tmp["pv"] = hlc3 * tmp["volume"]
        cs_pv = tmp.groupby("date")["pv"].expanding().sum().reset_index(level=0, drop=True)
        cs_vol = tmp.groupby("date")["volume"].expanding().sum().reset_index(level=0, drop=True)
        return (cs_pv / cs_vol).reindex(df.index)
    # daily+: rolling 20-period volume-weighted price as VWAP proxy
    pv = hlc3 * df["volume"]
    return (pv.rolling(20, min_periods=10).sum() / df["volume"].rolling(20, min_periods=10).sum()).reindex(df.index)


def _swing_levels(series: pd.Series, order: int = 2) -> pd.Series:
    """Return swing level values indexed by their position."""
    idx = argrelextrema(series.values, np.greater, order=order)[0]
    return pd.Series(series.values[idx], index=series.index[idx])


def _nearest_cluster(spot: float, points: pd.Series, direction: int, min_touches: int = 2, tol_pct: float = 0.015):
    """Cluster swing points and return the nearest cluster above (direction=1) or below (direction=-1) spot."""
    if points.empty:
        return None
    vals = points.values
    clusters = []
    used = set()
    for i, v in enumerate(vals):
        if i in used:
            continue
        members = [j for j, w in enumerate(vals) if abs(w / v - 1) <= tol_pct]
        if len(members) >= min_touches:
            clusters.append(float(np.mean(vals[members])))
        used.update(members)
    if direction == 1:
        candidates = [c for c in clusters if c > spot]
    else:
        candidates = [c for c in clusters if c < spot]
    if not candidates:
        return None
    return min(candidates, key=lambda c: abs(c - spot))


def synthetic_walls(df: pd.DataFrame, lookback: int = 80, order: int = 3) -> pd.DataFrame:
    """Compute synthetic call/put walls from recent swing highs/lows."""
    out = pd.DataFrame(index=df.index)
    call_wall = np.full(len(df), np.nan)
    put_wall = np.full(len(df), np.nan)
    for i in range(lookback, len(df)):
        window_high = df["high"].iloc[i - lookback : i + 1]
        window_low = df["low"].iloc[i - lookback : i + 1]
        spot = float(df["close"].iloc[i])
        highs = _swing_levels(window_high, order)
        lows = _swing_levels(window_low * -1, order) * -1
        call_wall[i] = _nearest_cluster(spot, highs, 1) or spot * 1.05
        put_wall[i] = _nearest_cluster(spot, lows, -1) or spot * 0.95
    out["call_wall"] = call_wall
    out["put_wall"] = put_wall
    return out


def load_data(symbol: str, period: str, interval: str) -> pd.DataFrame:
    df = yf.download(symbol, period=period, interval=interval, auto_adjust=True, progress=False)
    if df is None or df.empty:
        raise RuntimeError(f"no data for {symbol} {period} {interval}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [str(c).lower() for c in df.columns]
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df.dropna(subset=["open", "high", "low", "close", "volume"])
    df["volume"] = df["volume"].astype(float).clip(lower=1)
    return df


def build_features(df: pd.DataFrame, interval: str, wall_lookback: int = 80) -> pd.DataFrame:
    f = df.copy()
    f["ema9"] = _ema(f["close"], 9)
    f["ema21"] = _ema(f["close"], 21)
    f["ema50"] = _ema(f["close"], 50)
    f["vwap"] = compute_vwap(f, interval)
    f["atr"] = _atr(f, 14)
    f["vol_sma20"] = f["volume"].rolling(20, min_periods=10).mean()
    walls = synthetic_walls(f, lookback=wall_lookback)
    f["call_wall"] = walls["call_wall"]
    f["put_wall"] = walls["put_wall"]
    return f


def generate_signals(f: pd.DataFrame, wall_atr: float = 0.75) -> pd.DataFrame:
    """Trend + VWAP/volume + gamma-wall filter. Signal fires only on transitions.

    Long: bull EMA stack (9>21>50), EMA9 crossing above EMA21, close above EMA9
    and VWAP, volume above average, green candle.  Avoid the synthetic call wall.
    Short is the mirror.
    """
    close = f["close"]
    e9, e21, e50 = f["ema9"], f["ema21"], f["ema50"]
    bull_stack = (e9 > e21) & (e21 > e50)
    bear_stack = (e9 < e21) & (e21 < e50)

    vwap = f["vwap"]
    vol_ok = f["volume"] > f["vol_sma20"]
    green = close >= f["open"]
    red = close <= f["open"]

    atr = f["atr"].replace(0, np.nan)
    call_dist = (f["call_wall"] - close) / atr
    put_dist = (close - f["put_wall"]) / atr
    # ok if we are well above the wall (broken) or well below (room to run)
    call_wall_ok = (call_dist < -0.25) | (call_dist > wall_atr) | call_dist.isna()
    put_wall_ok = (put_dist < -0.25) | (put_dist > wall_atr) | put_dist.isna()

    # EMA crossover entry in aligned EMA trend, with VWAP/volume confluence
    # and call/put wall guard.  Enters on the cross of EMA9 over EMA21.
    long_cond = (
        bull_stack
        & (e9 > e21)
        & (e9.shift(1) <= e21.shift(1))
        & (close > e9)
        & (close > vwap)
        & green
        & vol_ok
        & call_wall_ok
    )
    short_cond = (
        bear_stack
        & (e9 < e21)
        & (e9.shift(1) >= e21.shift(1))
        & (close < e9)
        & (close < vwap)
        & red
        & vol_ok
        & put_wall_ok
    )

    # transitions only: one entry per fresh setup
    long_cond = long_cond.astype(bool)
    short_cond = short_cond.astype(bool)
    long_entry = long_cond & ~long_cond.shift(1).fillna(False)
    short_entry = short_cond & ~short_cond.shift(1).fillna(False)

    sig = pd.Series(0, index=f.index, dtype=int)
    sig.loc[long_entry] = 1
    sig.loc[short_entry] = -1
    return f.assign(signal=sig)


def backtest(
    f: pd.DataFrame,
    initial_cash: float = 100_000.0,
    commission: float = 0.001,
    stop_atr_mult: float = 2.0,
    target_atr_mult: float = 4.0,
    max_hold: int = 30,
    cooldown: int = 3,
) -> tuple:
    trades = []
    equity = [initial_cash]
    pos = 0
    entry_px = entry_ts = None
    cooldown_left = 0
    peak = initial_cash
    max_dd = 0.0
    close = f["close"].astype(float)
    sig = f["signal"].astype(int)
    atr = f["atr"]
    e9, e21, e50 = f["ema9"], f["ema21"], f["ema50"]

    for i, ts in enumerate(f.index):
        px = float(close.iloc[i])
        s = int(sig.iloc[i])
        eq = equity[-1]
        peak = max(peak, eq)
        dd = (peak - eq) / peak
        max_dd = max(max_dd, dd)

        if cooldown_left > 0:
            cooldown_left -= 1

        if pos == 0:
            if s != 0 and cooldown_left == 0:
                entry_px = px
                entry_ts = ts
                pos = s
                equity.append(eq)
            else:
                equity.append(eq)
            continue

        ret = (px - entry_px) / entry_px if pos == 1 else (entry_px - px) / entry_px
        hold_bars = i - f.index.get_loc(entry_ts) if entry_ts in f.index else 0
        atr_val = float(atr.iloc[i]) if pd.notna(atr.iloc[i]) and atr.iloc[i] > 0 else 0.0
        stop = -stop_atr_mult * atr_val / entry_px if atr_val > 0 else -0.03
        target = target_atr_mult * atr_val / entry_px if atr_val > 0 else 0.06

        # trend break: EMA stack no longer supports the position
        trend_broken = False
        if pos == 1:
            trend_broken = not (e9.iloc[i] > e21.iloc[i] > e50.iloc[i])
        elif pos == -1:
            trend_broken = not (e9.iloc[i] < e21.iloc[i] < e50.iloc[i])

        exit_now = ret <= stop or ret >= target or trend_broken or hold_bars >= max_hold

        if exit_now and hold_bars > 0:
            net_ret = ret - 2.0 * commission
            pnl = eq * net_ret
            trades.append({
                "entry": entry_ts,
                "exit": ts,
                "side": "long" if pos == 1 else "short",
                "entry_px": entry_px,
                "exit_px": px,
                "ret": net_ret,
                "pnl": pnl,
                "hold_bars": hold_bars,
            })
            eq = eq + pnl
            equity.append(eq)
            pos = 0
            entry_px = entry_ts = None
            cooldown_left = cooldown
        else:
            equity.append(eq)

    # mark last open to equity
    if pos != 0:
        px = float(close.iloc[-1])
        ret = (px - entry_px) / entry_px if pos == 1 else (entry_px - px) / entry_px
        net_ret = ret - 2.0 * commission
        pnl = eq * net_ret
        equity[-1] = eq + pnl

    f = f.assign(equity=equity[1:])
    return f, trades


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol", default="SPY", nargs="?")
    parser.add_argument("--period", default="2y")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--initial-cash", type=float, default=100_000.0)
    parser.add_argument("--commission", type=float, default=0.001)
    parser.add_argument("--wall-atr", type=float, default=0.75)
    parser.add_argument("--stop-atr", type=float, default=2.0)
    parser.add_argument("--target-atr", type=float, default=4.0)
    parser.add_argument("--max-hold", type=int, default=30)
    parser.add_argument("--cooldown", type=int, default=3)
    parser.add_argument("--out", type=Path, default=OUT / "ema_vwap_volume_gex_backtest.json")
    args = parser.parse_args()

    print(f"loading {args.symbol} {args.interval} {args.period} ...")
    df = load_data(args.symbol, args.period, args.interval)
    print(f"rows={len(df)} from {df.index[0]} to {df.index[-1]}")

    f = build_features(df, interval=args.interval)
    f = generate_signals(f, wall_atr=args.wall_atr)
    f, trades = backtest(
        f,
        initial_cash=args.initial_cash,
        commission=args.commission,
        stop_atr_mult=args.stop_atr,
        target_atr_mult=args.target_atr,
        max_hold=args.max_hold,
        cooldown=args.cooldown,
    )

    if not trades:
        print("no trades generated")
        return

    tdf = pd.DataFrame(trades)
    wins = (tdf["pnl"] > 0).sum()
    longs = (tdf["side"] == "long").sum()
    shorts = (tdf["side"] == "short").sum()
    long_pnl = tdf.loc[tdf["side"] == "long", "pnl"].sum() if longs else 0.0
    short_pnl = tdf.loc[tdf["side"] == "short", "pnl"].sum() if shorts else 0.0
    final = float(f["equity"].iloc[-1])
    ret = final / args.initial_cash - 1.0
    peak = f["equity"].cummax()
    dd = (peak - f["equity"]) / peak
    max_dd = float(dd.max())

    result = BacktestResult(
        symbol=args.symbol,
        interval=args.interval,
        period=args.period,
        n_trades=len(trades),
        win_rate=wins / len(trades),
        final=final,
        total_ret=ret,
        max_dd=max_dd,
        avg_trade=float(tdf["pnl"].mean()),
        best=float(tdf["pnl"].max()),
        worst=float(tdf["pnl"].min()),
        avg_hold_bars=float(tdf["hold_bars"].mean()),
        longs=int(longs),
        shorts=int(shorts),
        long_pnl=float(long_pnl),
        short_pnl=float(short_pnl),
    )

    print("\n--- backtest result ---")
    print(json.dumps(asdict(result), indent=2, default=str))
    args.out.write_text(json.dumps(asdict(result), indent=2, default=str))
    print(f"\nsaved result to {args.out}")


if __name__ == "__main__":
    main()
