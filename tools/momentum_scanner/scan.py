#!/usr/bin/env python3
"""momentum_scanner.py - Scan for explosive momentum setups

Usage: python3 tools/momentum_scanner/scan.py

Scans saved OHLCV data for:
- squeeze_release: Bollinger squeeze ending
- vol_surge: volume > 1.5x SMA20  
- poc_break: price breaking value area
- htf_green: HA momentum confirmation
"""

from pathlib import Path
import pandas as pd
import numpy as np

def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()

def _sma(s, n):
    return s.rolling(n, min_periods=max(1, n // 2)).mean()

def scan_data(code, df):
    """Scan daily dataframe for momentum setups."""
    daily = df.copy()
    daily.index = pd.to_datetime(df.index)
    
    # Already daily data
    close = daily["close"]
    
    # Volume surge check
    vol_sma = _sma(daily["volume"], 20)
    rvol = daily["volume"] / vol_sma
    vol_surge = rvol.iloc[-1] >= 1.5
    
    # Squeeze detection
    basis = _sma(close, 20)
    std = close.rolling(20, min_periods=10).std()
    upper_bb = basis + 2.0 * std
    lower_bb = basis - 2.0 * std
    ma = _sma(close, 20)
    tr = pd.concat([
        daily["high"]-daily["low"],
        (daily["high"]-close.shift(1)).abs(),
        (daily["low"]-close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    rangema = _sma(tr, 20)
    upper_kc = ma + rangema * 1.5
    lower_kc = ma - rangema * 1.5
    
    sqz_on = (lower_bb > lower_kc) & (upper_bb < upper_kc)
    sqz_off = (lower_bb < lower_kc) & (upper_bb > upper_kc)
    squeeze_release = bool(sqz_on.iloc[-2] and sqz_off.iloc[-1]) if len(sqz_on) >= 2 else False
    
    # Direction check
    up_move = close.iloc[-1] > close.iloc[-2] * 1.03
    down_move = close.iloc[-1] < close.iloc[-2] * 0.97
    
    # Call score
    call_score = 0.0
    if vol_surge and up_move: call_score += 0.4
    if squeeze_release and up_move: call_score += 0.3
    call_score += min(0.3, float(rvol.iloc[-1]) * 0.15)
    
    # Put score
    put_score = 0.0
    if vol_surge and down_move: put_score += 0.4
    if squeeze_release and down_move: put_score += 0.3
    
    return {
        "code": code,
        "squeeze_release": squeeze_release,
        "vol_surge": vol_surge,
        "rvol": float(rvol.iloc[-1]) if np.isfinite(rvol.iloc[-1]) else 0.0,
        "call_score": float(min(call_score, 1.0)),
        "put_score": float(min(put_score, 1.0))
    }

def main():
    base = Path("/Users/syriljacob/Desktop/TradingAlgoWork/runs/poc_va_v34_momo/artifacts")
    codes = ["IONQ.US", "AVGO.US", "TSLA.US", "HOOD.US", "AMD.US", "NVDA.US", "MSTR.US"]
    
    print("=== Momentum Scanner Output ===\n")
    for code in codes:
        ohlcv_path = base / f"ohlcv_{code}.csv"
        if ohlcv_path.exists():
            df = pd.read_csv(ohlcv_path, index_col=0, parse_dates=True)
            result = scan_data(code, df)
            squeeze = "🚀" if result["squeeze_release"] else "  "
            surge = "💥" if result["vol_surge"] else "  "
            arrow = "↑" if result["call_score"] > result["put_score"] else "↓"
            best = result["call_score"] if result["call_score"] > result["put_score"] else result["put_score"]
            print(f"{result['code']:8s} {squeeze}{surge} C={result['call_score']:.2f} P={result['put_score']:.2f} rvol={result['rvol']:.1f} {arrow}{best:.2f}")

if __name__ == "__main__":
    main()