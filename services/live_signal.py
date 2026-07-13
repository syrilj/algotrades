#!/usr/bin/env python3
"""Live signal engine for any ticker - no training required.
Dynamic features computed on-the-fly. Works with options_picker.

Usage:
    from services.live_signal import LiveSignalEngine
    signal = LiveSignalEngine()
    result = signal.analyze("IONQ.US")
    if result['go_long'] and result['vol_z'] >= 1.5:
        from tools.options_picker import propose
        plan = propose("IONQ.US", account=1000, leverage=10)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf
from typing import Dict, Any


class LiveSignalEngine:
    """Universal signal engine - works on any ticker with yfinance data."""
    
    def __init__(self):
        # Conservative parameters for unknown symbols
        self.params = {
            'vol_z_threshold': 1.5,
            'min_confidence': 0.5,
            'vol_lookback': 20,
            'swing_period': 20,
        }
    
    def _ema(self, s: pd.Series, n: int) -> pd.Series:
        return s.ewm(span=n, adjust=False).mean()
    
    def _sma(self, s: pd.Series, n: int) -> pd.Series:
        return s.rolling(n, min_periods=max(1, n // 2)).mean()
    
    def _atr(self, df: pd.DataFrame) -> pd.Series:
        high = df['High']
        low = df['Low']
        close = df['Close']
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs()
        ], axis=1).max(axis=1)
        return self._sma(tr, 14)
    
    def _macd_hist(self, df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.Series:
        ema_fast = self._ema(df['Close'], fast)
        ema_slow = self._ema(df['Close'], slow)
        macd = ema_fast - ema_slow
        return macd - self._ema(macd, signal)
    
    def _vol_z(self, volume: pd.Series, lookback: int = 20) -> float:
        vol_sma = self._sma(volume, lookback)
        vol_std = volume.rolling(lookback, min_periods=5).std()
        if vol_std.iloc[-1] <= 0:
            return 0.0
        return float((volume.iloc[-1] - vol_sma.iloc[-1]) / vol_std.iloc[-1])
    
    def _swing_vwap(self, df: pd.DataFrame, period: int = 20) -> Dict[str, Any]:
        """Compute swing VWAP and uptrend."""
        typical = (df['High'] + df['Low'] + df['Close']) / 3
        volume = df['Volume']
        
        vwap = (typical * volume).rolling(period, min_periods=5).sum() / volume.rolling(period, min_periods=5).sum()
        vwap_prev = vwap.shift(1)
        uptrend = vwap > vwap_prev
        
        return {'vwap': vwap.iloc[-1], 'uptrend': bool(uptrend.iloc[-1])}
    
    def analyze(self, symbol: str, df: pd.DataFrame | None = None) -> Dict[str, Any]:
        """Analyze a symbol and return signal dict.

        If ``df`` is provided it must have columns Open, High, Low, Close, Volume
        with a DatetimeIndex. Otherwise the engine fetches from yfinance.

        Returns:
            {
                'symbol': str,
                'go_long': bool,
                'confidence': float (0-1),
                'vol_z': float,
                'atr_pct': float,
                'above_vwap': bool,
                'swing_uptrend': bool,
                'macd_positive': bool,
                'price': float,
                'signal_strength': float (position multiplier)
            }
        """
        sym = symbol.upper().replace(".US", "")

        # Fetch data if not supplied
        if df is None:
            try:
                ticker = yf.Ticker(sym)
                df = ticker.history(period="60d", interval="1h")
            except Exception as e:
                return {'symbol': symbol, 'error': str(e)}

        if df.empty or len(df) < 20:
            return {'symbol': symbol, 'error': 'no_data'}
        
        # Calculate features
        vol_z = self._vol_z(df['Volume'], self.params['vol_lookback'])
        atr = self._atr(df)
        atr_pct = float(atr.iloc[-1] / df['Close'].iloc[-1])
        
        macd_hist = self._macd_hist(df)
        above_vwap_data = self._swing_vwap(df)
        
        above_vwap = bool(df['Close'].iloc[-1] > above_vwap_data['vwap'])
        swing_up = bool(above_vwap_data['uptrend'])
        macd_pos = bool(macd_hist.iloc[-1] > 0)
        bullish_bar = bool(df['Close'].iloc[-1] > df['Open'].iloc[-1])
        # Research-backed: vol expand is strongest meta (VOLUME_Z_META); VWAP/MACD are side aids
        go_long = (
            vol_z >= self.params['vol_z_threshold'] and
            macd_pos and
            (above_vwap or swing_up) and
            bullish_bar
        )
        soft_long = macd_pos and (above_vwap or swing_up) and vol_z >= 0.5

        go_short = (
            vol_z >= self.params['vol_z_threshold'] and
            (not macd_pos) and
            (not above_vwap or not swing_up) and
            (not bullish_bar)
        )
        soft_short = (not macd_pos) and (not above_vwap or not swing_up) and vol_z >= 0.5

        # Confidence Long
        conf_l = 0.0
        conf_l += min(0.45, max(0.0, vol_z / 4.0) * 0.45 / 0.5)
        if macd_pos:
            conf_l += 0.20
        if above_vwap:
            conf_l += 0.15
        if swing_up:
            conf_l += 0.10
        if bullish_bar:
            conf_l += 0.10
        confidence = float(min(1.0, max(0.0, conf_l)))

        # Confidence Short
        conf_s = 0.0
        conf_s += min(0.45, max(0.0, vol_z / 4.0) * 0.45 / 0.5)
        if not macd_pos:
            conf_s += 0.20
        if not above_vwap:
            conf_s += 0.15
        if not swing_up:
            conf_s += 0.10
        if not bullish_bar:
            conf_s += 0.10
        confidence_bear = float(min(1.0, max(0.0, conf_s)))

        signal_strength = 0.0
        if go_long:
            if vol_z >= 2.5:
                signal_strength = 10.0
            elif vol_z >= 2.0:
                signal_strength = 5.0
            elif vol_z >= 1.5:
                signal_strength = 3.0
        elif soft_long:
            signal_strength = 1.0

        signal_strength_bear = 0.0
        if go_short:
            if vol_z >= 2.5:
                signal_strength_bear = 10.0
            elif vol_z >= 2.0:
                signal_strength_bear = 5.0
            elif vol_z >= 1.5:
                signal_strength_bear = 3.0
        elif soft_short:
            signal_strength_bear = 1.0

        return {
            'symbol': symbol,
            'go_long': go_long,
            'soft_long': soft_long,
            'go_short': go_short,
            'soft_short': soft_short,
            'confidence': round(confidence, 2),
            'confidence_bear': round(confidence_bear, 2),
            'vol_z': round(vol_z, 2),
            'atr_pct': round(atr_pct, 4),
            'above_vwap': above_vwap,
            'swing_uptrend': swing_up,
            'macd_positive': macd_pos,
            'price': round(float(df['Close'].iloc[-1]), 2),
            'signal_strength': signal_strength,
            'signal_strength_bear': signal_strength_bear,
            'timestamp': df.index[-1].isoformat(),
        }


def batch_scan(symbols: list) -> list:
    """Scan multiple symbols and return signals sorted by strength."""
    engine = LiveSignalEngine()
    results = [engine.analyze(s) for s in symbols]
    return sorted(
        [r for r in results if r.get('go_long')],
        key=lambda x: x['signal_strength'],
        reverse=True
    )


if __name__ == "__main__":
    # Test on the winners
    signals = batch_scan(['IONQ.US', 'APLD.US', 'META.US', 'TSLA.US'])
    for s in signals:
        print(f"{s['symbol']}: vol_z={s['vol_z']}, strength={s['signal_strength']}, price={s['price']}")
    
    # Test single symbol
    import sys
    if len(sys.argv) > 1:
        print(f"\nDetailed for {sys.argv[1]}:")
        print(LiveSignalEngine().analyze(sys.argv[1]))