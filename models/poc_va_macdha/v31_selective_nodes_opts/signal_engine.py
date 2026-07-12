"""v31_selective_nodes_opts — selective node reaction on v28 options DNA.

Primary side: v21 specialists (POC/VA + HTF St.MACD-HA), then structure gate:
  EMA cloud bull + hold VAL/POC + upside magnet room + no OB chase past VAH.

Secondary size: conf tier × surgical macro × soft rvol mult; cooloff 10d.
DTE: 10 in high realized-vol percentile, else 14 (fixed adaptive).

Doctrine: selective at nodes, not active. Soft secondary only for vol.
AST-sandbox safe: no executable top-level assigns beyond imports/defs.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def _equity_engine_path() -> Path:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[1] / "v21_mstr_tsla" / "signal_engine.py",
        here.parents[3] / "models" / "poc_va_macdha" / "v21_mstr_tsla" / "signal_engine.py",
        Path("/Users/syriljacob/Desktop/TradingAlgoWork/models/poc_va_macdha/v21_mstr_tsla/signal_engine.py"),
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(f"v21 equity engine not found; tried {candidates}")


def _load_equity_engine():
    path = _equity_engine_path()
    spec = importlib.util.spec_from_file_location("v21_equity_se_v31", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod.SignalEngine()


def _load_macro(start: str, end: str):
    tools = Path(__file__).resolve().parents[3] / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    from econ_narrative import MacroNarrative  # noqa: WPS433

    return MacroNarrative(start=start, end=end)


def _to_daily_signal(sig: pd.Series) -> pd.Series:
    s = sig.copy()
    s.index = pd.to_datetime(s.index)
    if getattr(s.index, "tz", None) is not None:
        s.index = s.index.tz_localize(None)
    return s.resample("1D").last().dropna()


def _to_daily_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d.index = pd.to_datetime(d.index)
    if getattr(d.index, "tz", None) is not None:
        d.index = d.index.tz_localize(None)
    cols = [c for c in ("open", "high", "low", "close", "volume") if c in d.columns]
    if "close" not in cols:
        raise ValueError("OHLCV requires close")
    agg = {}
    if "open" in cols:
        agg["open"] = "first"
    if "high" in cols:
        agg["high"] = "max"
    if "low" in cols:
        agg["low"] = "min"
    agg["close"] = "last"
    if "volume" in cols:
        agg["volume"] = "sum"
    out = d[list(agg.keys())].resample("1D").agg(agg).dropna(subset=["close"])
    if "volume" not in out.columns:
        out["volume"] = 1.0
    if "high" not in out.columns:
        out["high"] = out["close"]
    if "low" not in out.columns:
        out["low"] = out["close"]
    if "open" not in out.columns:
        out["open"] = out["close"]
    return out


def _ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def _est_atm_premium(spot: float, iv: float = 0.55, dte: float = 14.0) -> float:
    t = max(dte, 1.0) / 365.0
    return float(max(spot * 0.4 * iv * np.sqrt(t), spot * 0.01, 0.25))


def _conf_tier(raw: float) -> float:
    r = float(raw)
    if r <= 0:
        return 0.0
    if r < 0.65:
        return 0.35
    if r < 0.78:
        return 0.65
    return 1.0


def _volume_profile_levels(highs, lows, volumes, rows, value_area_pct):
    lo = float(np.min(lows))
    hi = float(np.max(highs))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return np.nan, np.nan, np.nan
    step = (hi - lo) / max(rows, 1)
    if step <= 0:
        return np.nan, np.nan, np.nan
    vol_bins = np.zeros(rows, dtype=float)
    for h, l, v in zip(highs, lows, volumes):
        if not np.isfinite(h) or not np.isfinite(l) or not np.isfinite(v):
            continue
        a = int(np.clip(np.floor((l - lo) / step), 0, rows - 1))
        b = int(np.clip(np.floor((h - lo) / step), 0, rows - 1))
        if b < a:
            a, b = b, a
        share = float(v) / max(b - a + 1, 1)
        vol_bins[a : b + 1] += share
    poc_level = int(np.argmax(vol_bins))
    total = float(vol_bins.sum())
    if total <= 0:
        return np.nan, np.nan, np.nan
    target = total * float(value_area_pct)
    value = vol_bins[poc_level]
    above = below = poc_level
    while value < target and (above < rows - 1 or below > 0):
        up = vol_bins[above + 1] if above < rows - 1 else -1.0
        dn = vol_bins[below - 1] if below > 0 else -1.0
        if up >= dn:
            above = min(above + 1, rows - 1)
            value += max(up, 0.0)
        else:
            below = max(below - 1, 0)
            value += max(dn, 0.0)
    poc = lo + (poc_level + 0.5) * step
    vah = lo + (above + 1) * step
    val = lo + below * step
    return float(poc), float(vah), float(val)


def _prior_session_profile(df: pd.DataFrame, lookback: int, rows: int, value_area_pct: float) -> pd.DataFrame:
    n = len(df)
    poc = np.full(n, np.nan)
    vah = np.full(n, np.nan)
    val = np.full(n, np.nan)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    vols = df["volume"].to_numpy(dtype=float)
    for i in range(lookback, n):
        sl = slice(i - lookback, i)
        poc[i], vah[i], val[i] = _volume_profile_levels(
            highs[sl], lows[sl], vols[sl], rows, value_area_pct
        )
    return pd.DataFrame({"poc": poc, "vah": vah, "val": val}, index=df.index)


def _ma_cloud(close: pd.Series, fast: int, mid: int, slow: int) -> pd.DataFrame:
    ema_f = _ema(close, fast).shift(1)
    ema_m = _ema(close, mid).shift(1)
    ema_s = _ema(close, slow).shift(1)
    bull = (ema_f > ema_m) & (ema_m > ema_s) & (close >= ema_m)
    bear = (ema_f < ema_m) & (ema_m < ema_s) & (close <= ema_m)
    return pd.DataFrame(
        {
            "ema_fast": ema_f,
            "ema_mid": ema_m,
            "ema_slow": ema_s,
            "cloud_bull": bull.fillna(False),
            "cloud_bear": bear.fillna(False),
        },
        index=close.index,
    )


def _standardized_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal_len: int = 9) -> pd.DataFrame:
    """Pine-aligned standardized MACD + HA transform + signal/hist."""
    src_px = df["close"]
    hl = (df["high"] - df["low"]).replace(0, np.nan)
    macd = (_ema(src_px, fast) - _ema(src_px, slow)) / _ema(hl, slow) * 100.0
    macd = macd.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    macd_prev = macd.shift(1).fillna(macd)
    o = macd_prev
    h = np.maximum(macd, macd_prev)
    l = np.minimum(macd, macd_prev)
    c = macd
    ha_close = (o + h + l + c) / 4.0
    ha_open = pd.Series(index=df.index, dtype=float)
    ha_open.iloc[0] = (float(o.iloc[0]) + float(c.iloc[0])) / 2.0
    for i in range(1, len(df)):
        ha_open.iloc[i] = (ha_open.iloc[i - 1] + ha_close.iloc[i - 1]) / 2.0
    sig = _ema(ha_close, signal_len)
    hist = ha_close - sig
    return pd.DataFrame(
        {
            "macd": macd,
            "ha_close": ha_close,
            "ha_open": ha_open,
            "ha_green": ha_close > ha_open,
            "signal": sig,
            "hist": hist,
        },
        index=df.index,
    )


def _nearest_node_above(spot: float, nodes: Dict[str, float]) -> Tuple[Optional[str], float]:
    above = {k: v for k, v in nodes.items() if np.isfinite(v) and v > spot}
    if not above:
        return None, float("nan")
    name = min(above, key=above.get)
    return name, float(above[name])


def _support_held(spot: float, nodes: Dict[str, float]) -> bool:
    supports = []
    for key in ("val", "poc"):
        v = nodes.get(key)
        if v is not None and np.isfinite(v):
            supports.append(float(v))
    if not supports:
        return False
    return spot >= min(supports)


def _soft_vol_mult(rvol: float, ref: float, lo: float, hi: float) -> float:
    if not np.isfinite(rvol) or rvol <= 0:
        return 0.75
    # Map rvol relative to ref into [lo, hi]
    scaled = 0.55 + 0.45 * min(rvol / max(ref, 1e-9), 1.5)
    return float(np.clip(scaled, lo, hi))


def _build_structure(
    daily: pd.DataFrame,
    ema_fast: int,
    ema_mid: int,
    ema_slow: int,
    lookback: int,
    rows: int,
    value_area_pct: float,
    revt: float,
) -> pd.DataFrame:
    """Daily structure frame for selectivity + soft size."""
    levels = _prior_session_profile(daily, lookback, rows, value_area_pct)
    cloud = _ma_cloud(daily["close"], ema_fast, ema_mid, ema_slow)
    st = _standardized_macd(daily)
    vol_sma = daily["volume"].rolling(20, min_periods=10).mean()
    rvol = daily["volume"] / vol_sma
    ret = daily["close"].pct_change()
    rv20 = ret.rolling(20, min_periods=15).std() * np.sqrt(252)
    rv_pct = rv20.rolling(252, min_periods=60).apply(
        lambda s: float(s.rank(pct=True).iloc[-1]), raw=False
    )

    out = pd.DataFrame(index=daily.index)
    out["close"] = daily["close"]
    out["poc"] = levels["poc"]
    out["vah"] = levels["vah"]
    out["val"] = levels["val"]
    out["cloud_bull"] = cloud["cloud_bull"].astype(bool)
    out["cloud_bear"] = cloud["cloud_bear"].astype(bool)
    out["macd"] = st["macd"]
    out["ha_green"] = st["ha_green"].astype(bool)
    out["macd_ob"] = st["macd"] > revt
    out["macd_os"] = st["macd"] < -revt
    out["rvol"] = rvol
    out["rv_percentile"] = rv_pct

    # Precompute selectivity flags (vector-ish loop for room/support)
    support_ok = np.zeros(len(out), dtype=bool)
    room_ok = np.zeros(len(out), dtype=bool)
    chase_ob = np.zeros(len(out), dtype=bool)
    closes = out["close"].to_numpy(float)
    for i in range(len(out)):
        spot = float(closes[i])
        if not np.isfinite(spot) or spot <= 0:
            continue
        nodes = {
            "val": float(out["val"].iloc[i]) if pd.notna(out["val"].iloc[i]) else np.nan,
            "poc": float(out["poc"].iloc[i]) if pd.notna(out["poc"].iloc[i]) else np.nan,
            "vah": float(out["vah"].iloc[i]) if pd.notna(out["vah"].iloc[i]) else np.nan,
        }
        support_ok[i] = _support_held(spot, nodes)
        _name, tgt = _nearest_node_above(spot, nodes)
        if _name is not None and np.isfinite(tgt):
            room = (tgt - spot) / max(spot, 1e-12)
            room_ok[i] = room >= 0.0  # filled below with min room in engine
            # store target room in separate series later
        vah = nodes.get("vah", np.nan)
        past_vah = np.isfinite(vah) and spot > float(vah)
        chase_ob[i] = bool(out["macd_ob"].iloc[i]) and past_vah

    out["support_ok"] = support_ok
    out["room_ok_raw"] = room_ok
    out["chase_ob"] = chase_ob
    # room with min pct applied in engine using min_target_room_pct
    room_pct = np.full(len(out), np.nan)
    for i in range(len(out)):
        spot = float(closes[i])
        nodes = {
            "val": float(out["val"].iloc[i]) if pd.notna(out["val"].iloc[i]) else np.nan,
            "poc": float(out["poc"].iloc[i]) if pd.notna(out["poc"].iloc[i]) else np.nan,
            "vah": float(out["vah"].iloc[i]) if pd.notna(out["vah"].iloc[i]) else np.nan,
        }
        _n, tgt = _nearest_node_above(spot, nodes)
        if _n is not None and np.isfinite(tgt) and spot > 0:
            room_pct[i] = (tgt - spot) / spot
    out["room_pct"] = room_pct
    return out


class SignalEngine:
    """Options overlay: selective nodes on v21 side + v28 risk DNA."""

    def __init__(self):
        self.equity_engine = _load_equity_engine()
        cfg: Dict[str, Any] = {}
        for cand in (
            Path(__file__).resolve().parent / "hunt_config.json",
            Path(__file__).resolve().parents[1] / "hunt_config.json",
        ):
            if cand.exists():
                cfg = json.loads(cand.read_text())
                break
        self.initial_cash = float(cfg.get("initial_cash", 1_000_000.0))
        self.risk_pct = float(cfg.get("risk_pct", 0.10))
        self.dte_days = int(cfg.get("dte_days", 14))
        self.dte_high_vol = int(cfg.get("dte_high_vol", 10))
        self.otm_pct = float(cfg.get("otm_pct", 0.0))
        self.contract_mult = int(cfg.get("contract_multiplier", 100))
        self.halt_dd = float(cfg.get("halt_dd", 0.28))
        self.flatten_dd = float(cfg.get("flatten_dd", 0.42))
        self.max_contracts = int(cfg.get("max_contracts", 500))
        self.use_narrative = bool(cfg.get("use_narrative", True))
        self.narrative_mode = str(cfg.get("narrative_mode", "surgical"))
        self.use_conf_tier = bool(cfg.get("use_conf_tier", True))
        self.loss_cooloff_days = int(cfg.get("loss_cooloff_days", 10))
        self.use_node_selectivity = bool(cfg.get("use_node_selectivity", True))
        self.use_stmacd_ob_filter = bool(cfg.get("use_stmacd_ob_filter", True))
        self.use_soft_vol_size = bool(cfg.get("use_soft_vol_size", True))
        self.use_adaptive_dte = bool(cfg.get("use_adaptive_dte", True))
        self.ema_fast = int(cfg.get("ema_fast", 8))
        self.ema_mid = int(cfg.get("ema_mid", 21))
        self.ema_slow = int(cfg.get("ema_slow", 55))
        self.profile_lookback = int(cfg.get("profile_lookback", 20))
        self.profile_rows = int(cfg.get("profile_rows", 25))
        self.value_area_pct = float(cfg.get("value_area_pct", 0.70))
        self.min_target_room_pct = float(cfg.get("min_target_room_pct", 0.004))
        self.stmacd_revt = float(cfg.get("stmacd_revt", 100.0))
        self.vol_surge_ref = float(cfg.get("vol_surge_ref", 1.35))
        self.vol_regime_high = float(cfg.get("vol_regime_high", 0.75))
        self.soft_vol_size_min = float(cfg.get("soft_vol_size_min", 0.55))
        self.soft_vol_size_max = float(cfg.get("soft_vol_size_max", 1.25))
        self._macro = None

    def _get_dte(self, rv_pct: float) -> int:
        if self.use_adaptive_dte and np.isfinite(rv_pct) and rv_pct > self.vol_regime_high:
            return self.dte_high_vol
        return self.dte_days

    def _ensure_macro(self, start: str, end: str) -> None:
        if self._macro is not None or not self.use_narrative:
            return
        try:
            self._macro = _load_macro(start, end)
        except Exception:  # noqa: BLE001
            self._macro = None

    def _structure_allows(self, row: pd.Series) -> bool:
        if not self.use_node_selectivity:
            return True
        if not bool(row.get("cloud_bull", False)):
            return False
        if not bool(row.get("support_ok", False)):
            return False
        room = row.get("room_pct", np.nan)
        if not (np.isfinite(room) and float(room) >= self.min_target_room_pct):
            return False
        if self.use_stmacd_ob_filter and bool(row.get("chase_ob", False)):
            return False
        return True

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        stock = self.equity_engine.generate(data_map)
        daily_sigs: Dict[str, pd.Series] = {}
        structure: Dict[str, pd.DataFrame] = {}
        for code, sig in stock.items():
            if code not in data_map:
                continue
            daily_sigs[code] = _to_daily_signal(sig)
            daily = _to_daily_ohlcv(data_map[code])
            structure[code] = _build_structure(
                daily,
                self.ema_fast,
                self.ema_mid,
                self.ema_slow,
                self.profile_lookback,
                self.profile_rows,
                self.value_area_pct,
                self.stmacd_revt,
            )

        if not daily_sigs:
            return []

        idx = sorted(set().union(*[set(s.index) for s in daily_sigs.values()]))
        if idx:
            self._ensure_macro(
                str((pd.Timestamp(idx[0]) - pd.Timedelta(days=120)).date()),
                str((pd.Timestamp(idx[-1]) + pd.Timedelta(days=5)).date()),
            )

        equity = float(self.initial_cash)
        peak = equity
        open_legs: Dict[str, Dict[str, Any]] = {}
        out: List[Dict[str, Any]] = []
        prev_sig = {c: 0.0 for c in daily_sigs}
        last_loss: Dict[str, pd.Timestamp] = {}

        for ts in idx:
            date_str = str(pd.Timestamp(ts).date())
            ts = pd.Timestamp(ts)

            for code, leg in list(open_legs.items()):
                if code not in structure or ts not in structure[code].index:
                    continue
                spot = float(structure[code].loc[ts, "close"])
                if not np.isfinite(spot) or spot <= 0:
                    continue
                leg["mtm"] = leg["qty"] * self.contract_mult * 0.5 * (spot - leg["entry_spot"])

            marked = equity + sum(l.get("mtm", 0.0) for l in open_legs.values())
            peak = max(peak, marked)
            dd = (peak - marked) / peak if peak > 0 else 0.0

            if dd >= self.flatten_dd and open_legs:
                for code, leg in list(open_legs.items()):
                    mtm = leg.get("mtm", 0.0)
                    if mtm < 0:
                        last_loss[code] = ts
                    out.append(
                        {
                            "date": date_str,
                            "action": "close",
                            "underlying": code,
                            "legs": [
                                {
                                    "type": "call",
                                    "strike": leg["strike"],
                                    "expiry": leg["expiry"],
                                    "qty": leg["qty"],
                                }
                            ],
                        }
                    )
                    equity = max(equity + mtm, equity * 0.01)
                    del open_legs[code]
                peak = max(peak, equity)
                continue

            narr_m = 1.0
            allow = True
            if self.use_narrative and self._macro is not None:
                feat = self._macro.features_on(ts, mode=self.narrative_mode)
                narr_m = float(feat.get("size_mult", 1.0))
                allow = bool(feat.get("allow_entry", True))

            for code in daily_sigs:
                if ts not in daily_sigs[code].index or code not in structure:
                    continue
                if ts not in structure[code].index:
                    continue
                raw = float(daily_sigs[code].loc[ts])
                row = structure[code].loc[ts]
                spot = float(row["close"])
                if not np.isfinite(spot) or spot <= 0:
                    continue
                was = prev_sig[code]
                prev_sig[code] = raw
                entering = was <= 0 and raw > 0
                exiting = was > 0 and raw <= 0

                # Structure exits: cloud flip bear while in trade
                if code in open_legs and bool(row.get("cloud_bear", False)):
                    exiting = True

                if exiting and code in open_legs:
                    leg = open_legs.pop(code)
                    mtm = leg.get("mtm", 0.0)
                    if mtm < 0:
                        last_loss[code] = ts
                    out.append(
                        {
                            "date": date_str,
                            "action": "close",
                            "underlying": code,
                            "legs": [
                                {
                                    "type": "call",
                                    "strike": leg["strike"],
                                    "expiry": leg["expiry"],
                                    "qty": leg["qty"],
                                }
                            ],
                        }
                    )
                    equity = max(equity + mtm, equity * 0.01)
                    peak = max(peak, equity)
                    continue

                if entering and code not in open_legs:
                    if dd >= self.halt_dd or not allow:
                        continue
                    if self.loss_cooloff_days > 0 and code in last_loss:
                        if (ts - last_loss[code]).days < self.loss_cooloff_days:
                            continue
                    if not self._structure_allows(row):
                        continue

                    conf_m = _conf_tier(raw) if self.use_conf_tier else min(float(raw), 1.0)
                    if conf_m <= 0:
                        continue
                    vol_m = 1.0
                    if self.use_soft_vol_size:
                        vol_m = _soft_vol_mult(
                            float(row.get("rvol", np.nan)),
                            self.vol_surge_ref,
                            self.soft_vol_size_min,
                            self.soft_vol_size_max,
                        )
                    # Mild OS reclaim preference (size up slightly)
                    if bool(row.get("macd_os", False)) and bool(row.get("ha_green", False)):
                        vol_m = min(vol_m * 1.1, self.soft_vol_size_max)

                    size_frac = conf_m * narr_m * vol_m
                    if size_frac <= 0.05:
                        continue

                    rv_pct = float(row.get("rv_percentile", 0.5))
                    if not np.isfinite(rv_pct):
                        rv_pct = 0.5
                    dte = self._get_dte(rv_pct)
                    prem = _est_atm_premium(spot, dte=float(dte))
                    budget = max(equity * self.risk_pct * size_frac, 0.0)
                    qty = int(budget / (prem * self.contract_mult))
                    qty = int(np.clip(qty, 0, self.max_contracts))
                    if qty < 1:
                        continue
                    expiry = (ts + pd.Timedelta(days=dte)).strftime("%Y-%m-%d")
                    strike = float(round(spot * (1.0 + self.otm_pct)))
                    out.append(
                        {
                            "date": date_str,
                            "action": "open",
                            "underlying": code,
                            "legs": [
                                {
                                    "type": "call",
                                    "strike": strike,
                                    "expiry": expiry,
                                    "qty": qty,
                                }
                            ],
                        }
                    )
                    open_legs[code] = {
                        "strike": strike,
                        "expiry": expiry,
                        "qty": qty,
                        "entry_spot": spot,
                        "mtm": 0.0,
                    }
                    equity -= qty * prem * self.contract_mult
                    equity = max(equity, self.initial_cash * 0.01)

        return out
