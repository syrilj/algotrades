"""Build REAL v13 specialist long candidates with engine-exit PnL labels.

Unlike poc_va_xgb (synthetic HA∧VWAP∧POC + fake 5-bar labels), this logs
entries only when v13 SignalEngine routing would fire, then simulates the
same exit rules to label y = 1 if round-trip PnL after cost > 0.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[2]
ART = Path(__file__).resolve().parent / "artifacts"
ART.mkdir(parents=True, exist_ok=True)

TICKERS = {
    "TSLA.US": "TSLA",
    "ARM.US": "ARM",
    "MU.US": "MU",
    "SPY.US": "SPY",
    "IONQ.US": "IONQ",
    "APLD.US": "APLD",
}
START = None  # 1h capped at 730d by Yahoo
END = "2026-07-11"
INTERVAL = "1h"
PERIOD = "730d"
COST = 0.002  # round-trip
MAX_HOLD = 60
PT_ATR = 1.5
SL_ATR = 1.0


def _load_v13():
    path = ROOT / "models" / "poc_va_macdha" / "v13_specialists" / "signal_engine.py"
    spec = importlib.util.spec_from_file_location("v13_specialists_se", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["v13_specialists_se"] = mod
    spec.loader.exec_module(mod)
    return mod


def fetch_ohlcv(ysym: str) -> pd.DataFrame:
    # Yahoo 1h max ~730 calendar days; pin start to avoid IPO/period edge failures
    end = pd.Timestamp(END)
    start = end - pd.Timedelta(days=729)
    raw = yf.download(
        ysym,
        start=start.strftime("%Y-%m-%d"),
        end=END,
        interval=INTERVAL,
        auto_adjust=True,
        progress=False,
    )
    if raw is None or raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [
            c[0].lower() if isinstance(c, tuple) else str(c).lower() for c in raw.columns
        ]
    else:
        raw.columns = [str(c).lower() for c in raw.columns]
    need = ["open", "high", "low", "close", "volume"]
    for c in need:
        if c not in raw.columns:
            return pd.DataFrame()
    df = raw[need].copy()
    df.index = pd.to_datetime(df.index)
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    return df.dropna(subset=["close"])


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    prev = c.shift(1)
    tr = pd.concat([(h - l), (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(span=n, adjust=False).mean()


def extract_candidates(
    code: str,
    raw_1h: pd.DataFrame,
    v13: Any,
    spy_htf_1h: pd.Series | None,
) -> pd.DataFrame:
    """Mirror v13 _signals_on_frame; emit one row per long entry with labels."""
    cfg = v13._ROUTING.get(code, v13._ROUTING.get("SPY.US", {}))
    data = raw_1h.copy()
    data.index = pd.to_datetime(data.index)
    if getattr(data.index, "tz", None) is not None:
        data.index = data.index.tz_localize(None)
    data = data.sort_index()
    signal_tf = cfg.get("signal_tf", "2h")
    frame = v13._resample_ohlcv(data, signal_tf) if signal_tf else data
    if frame.empty or len(frame) < 80:
        return pd.DataFrame()

    value_area_pct = cfg.get("value_area_pct", 0.7)
    profile_rows = int(cfg.get("profile_rows", 25))
    profile_lookback = int(cfg.get("profile_lookback", 20))
    macd_fast = int(cfg.get("macd_fast", 12))
    macd_slow = int(cfg.get("macd_slow", 26))
    macd_signal = int(cfg.get("macd_signal", 9))
    macd_htf = cfg.get("macd_htf", "4h")
    require_htf_green = bool(cfg.get("require_htf_green", True))
    require_vwap_uptrend = bool(cfg.get("require_vwap_uptrend", False))
    require_above_vwap = bool(cfg.get("require_above_vwap", False))
    require_volume_expand = bool(cfg.get("require_volume_expand", False))
    require_vol_confirm = bool(cfg.get("require_vol_confirm", False))
    block_red_flag = bool(cfg.get("block_red_flag", False))
    block_dump = bool(cfg.get("block_dump", False))
    require_sqz_release = bool(cfg.get("require_sqz_release", False))
    require_mom_pos = bool(cfg.get("require_mom_pos", False))
    require_mom_pos_inc = bool(cfg.get("require_mom_pos_inc", False))
    allow_healthy_pull_entry = bool(cfg.get("allow_healthy_pull_entry", False))
    exit_on_poc_break = bool(cfg.get("exit_on_poc_break", False))
    exit_on_val_break = bool(cfg.get("exit_on_val_break", False))
    exit_below_vwap = bool(cfg.get("exit_below_vwap", False))
    exit_on_sqz_neg = bool(cfg.get("exit_on_sqz_neg", False))
    soft_confidence = bool(cfg.get("soft_confidence", False))
    swing_period = int(cfg.get("swing_period", 50))
    vol_look = int(cfg.get("vol_look", 5))
    vol_sma = int(cfg.get("vol_sma", 20))
    min_confidence = float(cfg.get("min_confidence", 0.6))

    levels = v13._prior_session_profile(frame, profile_lookback, profile_rows, value_area_pct)
    poc, vah, val = levels["poc"], levels["vah"], levels["val"]
    close = frame["close"]
    poc_ok = (close >= poc) & poc.notna()
    in_va = (close >= val) & (close <= vah) & val.notna()
    htf = v13._htf_ha_green(frame, macd_htf, macd_fast, macd_slow, macd_signal)
    local_ha = v13._standardized_macd_ha(frame, macd_fast, macd_slow, macd_signal)
    macd_hist = local_ha["macd"] - v13._ema(local_ha["macd"], macd_signal)
    swing = v13.dynamic_swing_anchored_vwap(frame, swing_period)
    vwap = swing["vwap"].shift(1)
    uptrend = swing["uptrend"].shift(1).fillna(False).astype(bool)
    above_vwap = (close >= vwap).fillna(False)
    vp = v13.volume_price_state(frame, vol_look, vol_sma)
    sqz = v13.squeeze_momentum(frame)
    atr = _atr(frame).replace(0, np.nan)

    gates = [poc_ok, in_va]
    if require_htf_green:
        gates.append(htf)
    if require_vwap_uptrend:
        gates.append(uptrend)
    if require_above_vwap:
        gates.append(above_vwap)
    if require_volume_expand:
        gates.append(vp["vol_expand"])
    if require_vol_confirm:
        gates.append(
            vp["confirm_up"]
            | (allow_healthy_pull_entry & vp["healthy_pull"] & above_vwap)
        )
    if block_red_flag:
        gates.append(~vp["red_flag_up"])
    if block_dump:
        gates.append(~vp["dump"])
    if require_sqz_release:
        gates.append(sqz["sqz_release"] | sqz["sqz_off"])
    if require_mom_pos:
        gates.append(sqz["mom_pos"])
    if require_mom_pos_inc:
        gates.append(sqz["mom_pos_inc"])
    long_hard = gates[0]
    for g in gates[1:]:
        long_hard = long_hard & g

    if soft_confidence:
        parts = [
            poc_ok,
            in_va,
            htf,
            uptrend,
            above_vwap,
            vp["confirm_up"] | vp["healthy_pull"],
            ~vp["red_flag_up"],
            sqz["mom_pos"],
            sqz["sqz_off"] | sqz["sqz_release"],
        ]
        total = None
        for p in parts:
            total = p.astype(float) if total is None else total + p.astype(float)
        conf = total / float(len(parts))
        long_entry = poc_ok & in_va & (conf >= min_confidence)
        if block_red_flag:
            long_entry = long_entry & (~vp["red_flag_up"])
        if block_dump:
            long_entry = long_entry & (~vp["dump"])
        if require_htf_green:
            long_entry = long_entry & htf
    else:
        long_entry = long_hard
        conf = pd.Series(1.0, index=frame.index)

    spy_reg = pd.Series(np.nan, index=frame.index)
    if spy_htf_1h is not None and not spy_htf_1h.empty:
        spy_reg = spy_htf_1h.reindex(frame.index, method="ffill")

    rows: list[dict[str, Any]] = []
    in_pos = False
    entry_i = -1
    entry_px = np.nan
    n = len(frame)
    high = frame["high"]
    low = frame["low"]
    pending: dict[str, Any] | None = None

    for i in range(n):
        if not in_pos:
            if bool(long_entry.iloc[i]):
                in_pos = True
                entry_i = i
                entry_px = float(close.iloc[i])
                a0 = float(atr.iloc[i]) if pd.notna(atr.iloc[i]) else np.nan
                dist_poc = (
                    (entry_px - float(poc.iloc[i])) / a0
                    if pd.notna(poc.iloc[i]) and a0 == a0 and a0
                    else np.nan
                )
                dist_val = (
                    (entry_px - float(val.iloc[i])) / a0
                    if pd.notna(val.iloc[i]) and a0 == a0 and a0
                    else np.nan
                )
                dist_vwap = (
                    (entry_px - float(vwap.iloc[i])) / a0
                    if pd.notna(vwap.iloc[i]) and a0 == a0 and a0
                    else np.nan
                )
                pending = {
                    "code": code,
                    "entry_ts": frame.index[i],
                    "entry_px": entry_px,
                    "dist_poc": dist_poc,
                    "dist_val": dist_val,
                    "dist_vwap": dist_vwap,
                    "ha_green": float(bool(local_ha["ha_green"].iloc[i])),
                    "above_vwap": float(bool(above_vwap.iloc[i])),
                    "vol_expand": float(bool(vp["vol_expand"].iloc[i])),
                    "macd_hist": float(macd_hist.iloc[i])
                    if pd.notna(macd_hist.iloc[i])
                    else 0.0,
                    "block_red_flag_on": float(bool(vp["red_flag_up"].iloc[i])),
                    "htf_green": float(bool(htf.iloc[i])),
                    "atr_pct": float(a0 / entry_px) if entry_px and a0 == a0 else np.nan,
                    "conf": float(conf.iloc[i]),
                    "spy_htf_green": float(spy_reg.iloc[i])
                    if pd.notna(spy_reg.iloc[i])
                    else 0.0,
                    "_entry_atr": a0,
                }
        else:
            exit_now = False
            if require_htf_green and not bool(htf.iloc[i]):
                exit_now = True
            if exit_on_poc_break and not bool(poc_ok.iloc[i]):
                exit_now = True
            if exit_on_val_break and close.iloc[i] < val.iloc[i]:
                exit_now = True
            if (
                exit_below_vwap
                and pd.notna(vwap.iloc[i])
                and close.iloc[i] < vwap.iloc[i]
            ):
                exit_now = True
            if exit_on_sqz_neg and bool(sqz["mom_neg"].iloc[i]):
                exit_now = True
            if bool(local_ha["ha_red"].iloc[i]) and not bool(htf.iloc[i]):
                exit_now = True
            if block_red_flag and bool(vp["red_flag_up"].iloc[i]):
                exit_now = True
            if i - entry_i >= MAX_HOLD:
                exit_now = True

            if exit_now and pending is not None and entry_i >= 0:
                exit_px = float(close.iloc[i])
                pnl = (exit_px / entry_px) - 1.0 - COST
                hold = i - entry_i
                a0 = pending.get("_entry_atr", np.nan)
                tb_y = 0
                if a0 == a0 and a0 and entry_px:
                    pt = entry_px + PT_ATR * a0
                    sl = entry_px - SL_ATR * a0
                    hit = False
                    for j in range(entry_i + 1, i + 1):
                        if float(high.iloc[j]) >= pt:
                            tb_y = 1
                            hit = True
                            break
                        if float(low.iloc[j]) <= sl:
                            tb_y = 0
                            hit = True
                            break
                    if not hit:
                        tb_y = 1 if pnl > 0 else 0
                pending.pop("_entry_atr", None)
                pending.update(
                    {
                        "exit_ts": frame.index[i],
                        "exit_px": exit_px,
                        "pnl": pnl,
                        "hold_bars": hold,
                        "y": int(pnl > 0),
                        "y_tb": int(tb_y),
                        "year": int(pd.Timestamp(pending["entry_ts"]).year),
                    }
                )
                rows.append(pending)
                pending = None
                in_pos = False
                entry_i = -1

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def _spy_htf_series(v13: Any, spy_1h: pd.DataFrame) -> pd.Series:
    if spy_1h.empty:
        return pd.Series(dtype=float)
    return v13._htf_ha_green(spy_1h, "4h", 12, 26, 9).astype(float)


def main() -> None:
    v13 = _load_v13()
    spy_1h = fetch_ohlcv("SPY")
    spy_htf = _spy_htf_series(v13, spy_1h)
    parts = []
    for code, ysym in TICKERS.items():
        raw = spy_1h if code == "SPY.US" else fetch_ohlcv(ysym)
        if raw.empty:
            print(code, "NO_DATA")
            continue
        cand = extract_candidates(code, raw, v13, spy_htf)
        print(
            code,
            "n=",
            len(cand),
            "hit=",
            float(cand["y"].mean()) if len(cand) else None,
        )
        if len(cand):
            parts.append(cand)
    if not parts:
        raise SystemExit("No candidates built")
    out = pd.concat(parts, ignore_index=True)
    for code in TICKERS:
        out[f"sym_{code.split('.')[0]}"] = (out["code"] == code).astype(float)
    path = ART / "candidates.csv"
    out.to_csv(path, index=False)
    meta = {
        "n": int(len(out)),
        "hit_rate": float(out["y"].mean()),
        "avg_pnl": float(out["pnl"].mean()),
        "by_code": out.groupby("code")
        .agg(n=("y", "size"), hit=("y", "mean"), exp=("pnl", "mean"))
        .reset_index()
        .to_dict(orient="records"),
        "cost": COST,
        "max_hold": MAX_HOLD,
        "interval": INTERVAL,
        "period": PERIOD,
        "end": END,
        "label": "engine_exit_pnl_after_cost",
    }
    (ART / "candidates_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print("wrote", path, "n=", meta["n"], "hit=", meta["hit_rate"], "exp=", meta["avg_pnl"])


if __name__ == "__main__":
    main()
