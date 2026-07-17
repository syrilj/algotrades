"""v87_arete_orderflow: Arete price action + OHLCV order-flow confluence skeleton.

This is a frozen, non-ML implementation of the 6-step discretionary framework:

1. Top-down bias from SPY/QQQ trend plus symbol relative strength.
2. Pain-point zones from recent swing lows (causal rolling min).
3. Volume spike detection via volume z-score (v44 volume_price_state).
4. Arete trigger: bullish engulfing + higher-high at the zone.
5. Delta / CVD / absorption confirmation from v44-style OHLCV proxies.
6. Composite 0-100 score; long when score >= entry_score, sized by score.

All thresholds are pre-registered and must not be retuned after the holdout is
locked. The model is intended as a research skeleton to be frozen, stress-tested,
and either promoted or rejected under the repo's anti-overfit protocol.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Config defaults (overridden by config.json strategy block)
# ---------------------------------------------------------------------------
DEFAULT_PARAMS: Dict[str, Any] = {
    "signal_tf": None,           # e.g. "2h" for 1H input; None uses raw bars
    "vol_sma": 20,               # volume SMA lookback for z-score
    "pain_lookback": 20,         # recent swing high/low window
    "pain_band_atr": 1.0,        # how close price must be to a low (in ATR)
    "cvd_lookback": 50,          # cumulative volume delta window
    "order_flow_lookback": 100,  # v44 order_flow_state lookback
    "entry_score": 60,           # composite score entry threshold
    "exit_score": 35,            # score below which to close
    "max_weight": 0.35,          # per-symbol target cap
    "max_hold_bars": 12,         # time stop
    "stop_atr": 1.5,             # hard stop in ATR units
    "trail_arm_atr": 1.0,        # when to arm trailing stop
    "trail_atr": 2.5,            # trailing stop in ATR units
    "market_symbols": ["SPY.US", "QQQ.US"],
    "market_sma": 50,
    "min_bars": 80,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _sha256(path: Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_repo_root(anchor: Path) -> Optional[Path]:
    for p in (anchor.resolve(), *anchor.resolve().parents):
        if (p / "models" / "poc_va_macdha" / "v44_absorption").is_dir():
            return p
    return None


def _load_v44_module(self_dir: Path) -> Any:
    """Load v44 absorption helper functions from the vendored copy or repo root."""
    # dynamic_model_rank may have copied the dependency as v44_engine.py
    try:
        import v44_engine as v44  # type: ignore
        return v44
    except Exception:
        pass

    repo_root = _find_repo_root(self_dir)
    if repo_root is None:
        raise RuntimeError("Could not locate TradingAlgoWork repo root or v44_engine")
    v44_path = repo_root / "models" / "poc_va_macdha" / "v44_absorption" / "signal_engine.py"
    if not v44_path.is_file():
        raise RuntimeError(f"v44 absorption engine not found at {v44_path}")

    module_name = f"v44_arete_{_sha256(v44_path)[:8]}_{id(v44_path)}"
    spec = importlib.util.spec_from_file_location(module_name, str(v44_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load v44 engine from {v44_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_params(self_dir: Path) -> Dict[str, Any]:
    """Load strategy params, preferring the run_dir config over the model_dir config."""
    candidates = [self_dir / "config.json", self_dir.parent / "config.json"]
    cfg: Dict[str, Any] = {}
    for cand in candidates:
        if cand.exists():
            try:
                cfg = json.loads(cand.read_text(encoding="utf-8"))
            except Exception:
                cfg = {}
            break
    strategy = cfg.get("strategy", {}) if isinstance(cfg.get("strategy"), dict) else {}
    out = dict(DEFAULT_PARAMS)
    for k in DEFAULT_PARAMS:
        if k in strategy:
            out[k] = strategy[k]
        elif k in cfg:
            out[k] = cfg[k]
    return out


def _canonical_root(code: str) -> str:
    return code.upper().split(".")[0]


# ---------------------------------------------------------------------------
# Signal engine
# ---------------------------------------------------------------------------
class SignalEngine:
    """OHLCV-only Arete + order-flow confluence skeleton."""

    def __init__(self) -> None:
        self_dir = Path(__file__).resolve().parent
        self._params = _load_params(self_dir)
        self._v44: Optional[Any] = None
        try:
            self._v44 = _load_v44_module(self_dir)
        except Exception as exc:
            print(f"[v87] warning: could not load v44 helpers: {exc}")
        self.last_confidence: Dict[str, pd.Series] = {}
        self.last_score: Dict[str, pd.Series] = {}

    def _market_frames(
        self, data_map: Dict[str, pd.DataFrame]
    ) -> Dict[str, pd.DataFrame]:
        """Resample market context symbols to the signal timeframe."""
        out: Dict[str, pd.DataFrame] = {}
        if self._v44 is None:
            return out
        market_roots = [_canonical_root(s) for s in self._params.get("market_symbols", [])]
        for raw_code, frame in data_map.items():
            root = _canonical_root(raw_code)
            if root not in market_roots:
                continue
            df = frame.copy()
            df.index = pd.to_datetime(df.index)
            if getattr(df.index, "tz", None) is not None:
                df.index = df.index.tz_localize(None)
            df = df.sort_index()
            tf = self._params.get("signal_tf")
            out[raw_code] = self._v44._resample_ohlcv(df, tf) if tf else df
        return out

    def _topdown_score(
        self, frame: pd.DataFrame, market_frames: Dict[str, pd.DataFrame]
    ) -> pd.Series:
        """0-15 score for trend alignment with market and relative strength."""
        if not market_frames:
            return pd.Series(7.5, index=frame.index)

        score = pd.Series(0.0, index=frame.index)
        n = 0
        mkt_sma = self._params["market_sma"]
        for mkt in market_frames.values():
            if mkt is None or mkt.empty or "close" not in mkt.columns:
                continue
            mkt_close = mkt["close"].astype(float).reindex(frame.index).ffill()
            mkt_sma_ser = (
                mkt_close.rolling(mkt_sma, min_periods=max(5, mkt_sma // 2))
                .mean()
                .shift(1)
            )
            trend_ok = (mkt_close > mkt_sma_ser).fillna(False)

            rs = (frame["close"].astype(float) / mkt_close.replace(0, np.nan)).ffill()
            rs_trend = (rs > rs.shift(10)).fillna(False)
            score = score + (trend_ok & rs_trend).astype(float)
            n += 1

        if n == 0:
            return pd.Series(7.5, index=frame.index)
        return (score / n * 15.0).clip(0.0, 15.0)

    def _signals_on_frame(
        self,
        code: str,
        df: pd.DataFrame,
        market_frames: Dict[str, pd.DataFrame],
    ) -> tuple[pd.Series, pd.Series]:
        """Return (target_weight_series, score_series) for one symbol."""
        if df is None or df.empty or len(df) < self._params["min_bars"]:
            idx = df.index if df is not None else pd.DatetimeIndex([])
            return pd.Series(0.0, index=idx), pd.Series(0.0, index=idx)

        data = df.copy()
        data.index = pd.to_datetime(data.index)
        if getattr(data.index, "tz", None) is not None:
            data.index = data.index.tz_localize(None)
        data = data.sort_index()

        if self._v44 is None:
            return pd.Series(0.0, index=data.index), pd.Series(0.0, index=data.index)

        tf = self._params.get("signal_tf")
        frame = self._v44._resample_ohlcv(data, tf) if tf else data
        if frame.empty or len(frame) < self._params["min_bars"]:
            return pd.Series(0.0, index=data.index), pd.Series(0.0, index=data.index)

        o = frame["open"].astype(float)
        h = frame["high"].astype(float)
        l = frame["low"].astype(float)
        c = frame["close"].astype(float)

        # VPA + order-flow from v44
        vp = self._v44.volume_price_state(frame, look=3, vol_sma=self._params["vol_sma"])
        of = self._v44.order_flow_state(
            frame,
            lookback=self._params["order_flow_lookback"],
            short_len=20,
            mid_len=50,
            long_len=self._params["order_flow_lookback"],
        )
        atr = self._v44._atr(frame, 14).shift(1)

        # --- Pain-point zone (causal recent swing low) ---
        pain_low = l.rolling(self._params["pain_lookback"], min_periods=5).min().shift(1)
        band = (self._params["pain_band_atr"] * atr / c).fillna(0.02)
        near_low = (l <= pain_low * (1 + band)).fillna(False)

        # --- Arete trigger: bullish engulfing + higher high ---
        prev_o = o.shift(1)
        prev_c = c.shift(1)
        body = c - o
        prev_body = prev_c - prev_o
        bull_engulf = (
            (body > 0)
            & (prev_body < 0)
            & (o < prev_c)
            & (c > prev_o)
            & (body.abs() > prev_body.abs())
        ).fillna(False)
        higher_high = (h > h.shift(1)).fillna(False)
        # upthrust is a false breakout; let volume/delta score filter the rest
        bad_bar = vp["upthrust"].fillna(False)
        entry_setup = near_low & bull_engulf & higher_high & (~bad_bar)

        # --- Composite 0-100 score ---
        # Volume spike: z-score over 1.0 starts scoring, full by 3.0
        vol_z = vp["vol_z"].fillna(0.0)
        vol_score = ((vol_z - 1.0) / 2.0).clip(0.0, 1.0) * 25.0

        # Price action confirmation: clean engulfing at the zone
        pa_score = entry_setup.astype(float) * 25.0

        # Delta / footprint alignment: current-bar pressure plus CVD/flow context
        rng = (h - l).replace(0, np.nan)
        pressure = ((c - o) / rng * 100.0).fillna(0.0)
        cvd = of["cvd_bias"].fillna(0.0)
        flow = of["flow_score"].fillna(0.0)
        delta_score = (
            pressure.clip(0.0, 100.0) / 100.0 * 12.0
            + (cvd + 0.2).clip(0.0, 0.4) / 0.4 * 4.0
            + ((flow + 50.0) / 100.0).clip(0.0, 1.0) * 4.0
        ).clip(0.0, 20.0)

        # Absorption: positive absorption_bias means buying at the low
        abs_bias = of["absorption_bias"].fillna(0.0)
        absorption_score = ((abs_bias + 0.5) / 1.0).clip(0.0, 1.0) * 15.0

        # Top-down + relative strength
        topdown_score = self._topdown_score(frame, market_frames)

        score = (vol_score + pa_score + delta_score + absorption_score + topdown_score).clip(
            0.0, 100.0
        )

        # --- Trade management loop ---
        signal = pd.Series(0.0, index=frame.index)
        in_pos = False
        entry_px = np.nan
        peak_px = np.nan
        entry_atr = np.nan
        entry_bar = -1
        entry_size = 0.0

        max_weight = self._params["max_weight"]
        entry_score = self._params["entry_score"]
        exit_score = self._params["exit_score"]
        max_hold = self._params["max_hold_bars"]
        stop_atr = self._params["stop_atr"]
        arm_atr = self._params["trail_arm_atr"]
        trail_atr = self._params["trail_atr"]

        for i in range(len(frame)):
            px = float(c.iloc[i])
            a = float(atr.iloc[i]) if pd.notna(atr.iloc[i]) else px * 0.01
            sc = float(score.iloc[i])
            pr = float(pressure.iloc[i])
            cv = float(cvd.iloc[i])
            ab = float(abs_bias.iloc[i])

            if not in_pos:
                # Enter only on a high-confluence engulfing reversal at support
                if (
                    entry_setup.iloc[i]
                    and sc >= entry_score
                    and pr > 30.0
                    and cv > -0.2
                    and ab > -0.5
                ):
                    size = min(max_weight, (sc / 100.0) * max_weight)
                    if size > 0.0:
                        in_pos = True
                        entry_px = px
                        peak_px = px
                        entry_atr = a
                        entry_bar = i
                        entry_size = float(size)
                        signal.iloc[i] = entry_size
            else:
                peak_px = max(peak_px, px)
                hard_stop = px <= entry_px - stop_atr * entry_atr
                armed = peak_px >= entry_px + arm_atr * entry_atr
                trail_stop = armed and (px <= peak_px - trail_atr * entry_atr)
                score_exit = sc < exit_score
                flow_exit = pr < 0.0 and cv < -0.3
                time_exit = (i - entry_bar) >= max_hold

                if hard_stop or trail_stop or score_exit or flow_exit or time_exit:
                    in_pos = False
                    signal.iloc[i] = 0.0
                    entry_size = 0.0
                    entry_px = peak_px = entry_atr = np.nan
                    entry_bar = -1
                else:
                    signal.iloc[i] = entry_size

        if in_pos:
            signal.iloc[-1] = 0.0

        # Expand low-frequency decisions back to the original bar index
        sig = signal.reindex(data.index).ffill().fillna(0.0).astype(float)
        score_full = score.reindex(data.index).ffill().fillna(0.0).astype(float)
        return sig, score_full

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        out: Dict[str, pd.Series] = {}
        self.last_confidence = {}
        self.last_score = {}

        if self._v44 is None:
            for code, df in data_map.items():
                idx = df.index if df is not None else pd.DatetimeIndex([])
                out[code] = pd.Series(0.0, index=idx)
            return out

        market_frames = self._market_frames(data_map)

        for code, df in data_map.items():
            if df is None:
                out[code] = pd.Series(0.0, index=pd.DatetimeIndex([]))
                continue
            try:
                sig, score = self._signals_on_frame(code, df, market_frames)
            except Exception as exc:
                print(f"[v87] error generating {code}: {exc}")
                sig = pd.Series(0.0, index=df.index)
                score = pd.Series(0.0, index=df.index)
            out[code] = sig
            self.last_score[code] = score
            self.last_confidence[code] = (score / 100.0).clip(0.0, 1.0)

        return out
