"""v32_soft_react_opts — v28 DNA + soft node/St.MACD reaction (no hard entry kills).

Approach flip vs v31:
  - Never hard-block specialist entries for structure.
  - Size UP at good nodes / OS reclaim; size DOWN on weak structure / OB chase.
  - Optional: exit when cloud flips bear; adaptive DTE 10/14.

AST-sandbox safe.
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
    spec = importlib.util.spec_from_file_location("v21_equity_se_v32", path)
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
    need = ["open", "high", "low", "close", "volume"]
    for c in need:
        if c not in d.columns:
            if c == "volume":
                d[c] = 1.0
            elif c in ("open", "high", "low"):
                d[c] = d["close"]
    out = (
        d[need]
        .resample("1D")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["close"])
    )
    return out


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


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
    return float(lo + (poc_level + 0.5) * step), float(lo + (above + 1) * step), float(lo + below * step)


def _prior_profile(df: pd.DataFrame, lookback: int, rows: int, vap: float) -> pd.DataFrame:
    n = len(df)
    poc = np.full(n, np.nan)
    vah = np.full(n, np.nan)
    val = np.full(n, np.nan)
    highs = df["high"].to_numpy(float)
    lows = df["low"].to_numpy(float)
    vols = df["volume"].to_numpy(float)
    for i in range(lookback, n):
        sl = slice(i - lookback, i)
        poc[i], vah[i], val[i] = _volume_profile_levels(highs[sl], lows[sl], vols[sl], rows, vap)
    return pd.DataFrame({"poc": poc, "vah": vah, "val": val}, index=df.index)


def _ma_cloud(close: pd.Series, fast: int, mid: int, slow: int) -> pd.DataFrame:
    f = _ema(close, fast).shift(1)
    m = _ema(close, mid).shift(1)
    s = _ema(close, slow).shift(1)
    bull = (f > m) & (m > s) & (close >= m)
    bear = (f < m) & (m < s) & (close <= m)
    return pd.DataFrame({"cloud_bull": bull.fillna(False), "cloud_bear": bear.fillna(False)}, index=close.index)


def _stmacd(df: pd.DataFrame, fast: int = 12, slow: int = 26) -> pd.DataFrame:
    src = df["close"]
    hl = (df["high"] - df["low"]).replace(0, np.nan)
    macd = (_ema(src, fast) - _ema(src, slow)) / _ema(hl, slow) * 100.0
    macd = macd.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    prev = macd.shift(1).fillna(macd)
    o, h, l, c = prev, np.maximum(macd, prev), np.minimum(macd, prev), macd
    ha_c = (o + h + l + c) / 4.0
    ha_o = pd.Series(index=df.index, dtype=float)
    ha_o.iloc[0] = (float(o.iloc[0]) + float(c.iloc[0])) / 2.0
    for i in range(1, len(df)):
        ha_o.iloc[i] = (ha_o.iloc[i - 1] + ha_c.iloc[i - 1]) / 2.0
    return pd.DataFrame(
        {"macd": macd, "ha_green": ha_c > ha_o, "ha_red": ha_c < ha_o},
        index=df.index,
    )


def _support_held(spot: float, val: float, poc: float) -> bool:
    supports = [x for x in (val, poc) if np.isfinite(x)]
    if not supports:
        return False
    return spot >= min(supports)


def _room_pct(spot: float, val: float, poc: float, vah: float) -> float:
    above = [x for x in (val, poc, vah) if np.isfinite(x) and x > spot]
    if not above or spot <= 0:
        return float("nan")
    return (min(above) - spot) / spot


def _build_structure(daily: pd.DataFrame, cfg: Dict[str, Any]) -> pd.DataFrame:
    lookback = int(cfg.get("profile_lookback", 20))
    rows = int(cfg.get("profile_rows", 25))
    vap = float(cfg.get("value_area_pct", 0.70))
    revt = float(cfg.get("stmacd_revt", 100.0))
    levels = _prior_profile(daily, lookback, rows, vap)
    cloud = _ma_cloud(
        daily["close"],
        int(cfg.get("ema_fast", 8)),
        int(cfg.get("ema_mid", 21)),
        int(cfg.get("ema_slow", 55)),
    )
    st = _stmacd(daily)
    vol_sma = daily["volume"].rolling(20, min_periods=10).mean()
    rvol = daily["volume"] / vol_sma
    ret = daily["close"].pct_change()
    rv20 = ret.rolling(20, min_periods=15).std() * np.sqrt(252)
    rv_pct = rv20.rolling(252, min_periods=60).apply(
        lambda s: float(s.rank(pct=True).iloc[-1]), raw=False
    )

    n = len(daily)
    good = np.zeros(n, dtype=bool)
    chase = np.zeros(n, dtype=bool)
    room = np.full(n, np.nan)
    closes = daily["close"].to_numpy(float)
    for i in range(n):
        spot = float(closes[i])
        val = float(levels["val"].iloc[i]) if pd.notna(levels["val"].iloc[i]) else np.nan
        poc = float(levels["poc"].iloc[i]) if pd.notna(levels["poc"].iloc[i]) else np.nan
        vah = float(levels["vah"].iloc[i]) if pd.notna(levels["vah"].iloc[i]) else np.nan
        bull = bool(cloud["cloud_bull"].iloc[i])
        supp = _support_held(spot, val, poc)
        rp = _room_pct(spot, val, poc, vah)
        room[i] = rp
        min_room = float(cfg.get("min_target_room_pct", 0.004))
        good[i] = bull and supp and np.isfinite(rp) and rp >= min_room
        past_vah = np.isfinite(vah) and spot > vah
        chase[i] = bool(st["macd"].iloc[i] > revt) and past_vah

    out = pd.DataFrame(index=daily.index)
    out["close"] = daily["close"]
    out["cloud_bull"] = cloud["cloud_bull"].astype(bool)
    out["cloud_bear"] = cloud["cloud_bear"].astype(bool)
    out["structure_good"] = good
    out["chase_ob"] = chase
    out["macd_os"] = st["macd"] < -revt
    out["ha_green"] = st["ha_green"].astype(bool)
    out["rvol"] = rvol
    out["rv_percentile"] = rv_pct
    out["room_pct"] = room
    return out


class SignalEngine:
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
        self.cfg = cfg
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
        # Soft reaction knobs
        self.use_soft_structure = bool(cfg.get("use_soft_structure", True))
        self.struct_good_mult = float(cfg.get("struct_good_mult", 1.15))
        self.struct_weak_mult = float(cfg.get("struct_weak_mult", 0.55))
        self.use_soft_ob = bool(cfg.get("use_soft_ob", True))
        self.ob_chase_mult = float(cfg.get("ob_chase_mult", 0.40))
        self.use_os_boost = bool(cfg.get("use_os_boost", True))
        self.os_boost_mult = float(cfg.get("os_boost_mult", 1.12))
        self.use_soft_vol = bool(cfg.get("use_soft_vol", False))
        self.vol_ref = float(cfg.get("vol_surge_ref", 1.35))
        self.use_adaptive_dte = bool(cfg.get("use_adaptive_dte", True))
        self.vol_regime_high = float(cfg.get("vol_regime_high", 0.75))
        self.exit_on_cloud_bear = bool(cfg.get("exit_on_cloud_bear", False))
        self.need_structure = bool(cfg.get("need_structure", True))  # compute structure frame
        self._macro = None

    def _get_dte(self, rv_pct: float) -> int:
        if self.use_adaptive_dte and np.isfinite(rv_pct) and rv_pct > self.vol_regime_high:
            return self.dte_high_vol
        return self.dte_days

    def _structure_size_mult(self, row: pd.Series) -> float:
        m = 1.0
        if self.use_soft_structure:
            m *= self.struct_good_mult if bool(row.get("structure_good", False)) else self.struct_weak_mult
        if self.use_soft_ob and bool(row.get("chase_ob", False)):
            m *= self.ob_chase_mult
        if self.use_os_boost and bool(row.get("macd_os", False)) and bool(row.get("ha_green", False)):
            m *= self.os_boost_mult
        if self.use_soft_vol:
            rvol = float(row.get("rvol", np.nan))
            if np.isfinite(rvol) and rvol > 0:
                scaled = 0.6 + 0.4 * min(rvol / max(self.vol_ref, 1e-9), 1.4)
                m *= float(np.clip(scaled, 0.55, 1.25))
        return float(np.clip(m, 0.15, 1.5))

    def _ensure_macro(self, start: str, end: str) -> None:
        if self._macro is not None or not self.use_narrative:
            return
        try:
            self._macro = _load_macro(start, end)
        except Exception:  # noqa: BLE001
            self._macro = None

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        stock = self.equity_engine.generate(data_map)
        daily_sigs: Dict[str, pd.Series] = {}
        structure: Dict[str, pd.DataFrame] = {}
        for code, sig in stock.items():
            if code not in data_map:
                continue
            daily_sigs[code] = _to_daily_signal(sig)
            daily = _to_daily_ohlcv(data_map[code])
            if self.need_structure:
                structure[code] = _build_structure(daily, self.cfg)
            else:
                structure[code] = pd.DataFrame({"close": daily["close"]}, index=daily.index)

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
                if np.isfinite(spot) and spot > 0:
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
                            "legs": [{"type": "call", "strike": leg["strike"], "expiry": leg["expiry"], "qty": leg["qty"]}],
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
                if self.exit_on_cloud_bear and code in open_legs and bool(row.get("cloud_bear", False)):
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
                            "legs": [{"type": "call", "strike": leg["strike"], "expiry": leg["expiry"], "qty": leg["qty"]}],
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
                    conf_m = _conf_tier(raw) if self.use_conf_tier else min(float(raw), 1.0)
                    if conf_m <= 0:
                        continue
                    react_m = self._structure_size_mult(row) if self.need_structure else 1.0
                    size_frac = conf_m * narr_m * react_m
                    if size_frac <= 0.05:
                        continue
                    rv_pct = float(row.get("rv_percentile", 0.5)) if self.need_structure else 0.5
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
                            "legs": [{"type": "call", "strike": strike, "expiry": expiry, "qty": qty}],
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
