"""v30_feedback_pro — v28 proven + volume surge + adaptive DTE refinements.

Building on v28 winner (+104.1% return, DD -11.2%, Sharpe 1.40):
  - Add volume surge filter (BREAKOUT_PRECIPITANTS): rvol >= 1.35 or vol_expand+rising
  - Add EMA200 regime filter: price must be above 200 SMA (structural integrity)
  - Add adaptive DTE: 10 days in high vol regime, 14-21 in low vol

Hypothesis: Higher quality entries with same cooloff protection yield +110%+ return.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

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
    spec = importlib.util.spec_from_file_location("v21_equity_se_v30", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod.SignalEngine()


def _load_macro(start: str, end: str):
    tools = Path(__file__).resolve().parents[3] / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    from econ_narrative import MacroNarrative
    return MacroNarrative(start=start, end=end)


def _to_daily_signal(sig: pd.Series) -> pd.Series:
    s = sig.copy()
    s.index = pd.to_datetime(s.index)
    if getattr(s.index, "tz", None) is not None:
        s.index = s.index.tz_localize(None)
    return s.resample("1D").last().dropna()


def _to_daily_close(df: pd.DataFrame) -> pd.Series:
    d = df.copy()
    d.index = pd.to_datetime(d.index)
    if getattr(d.index, "tz", None) is not None:
        d.index = d.index.tz_localize(None)
    return d["close"].resample("1D").last().dropna()


def _est_atm_premium(spot: float, iv: float = 0.55, dte: float = 14.0) -> float:
    t = max(dte, 1.0) / 365.0
    return float(max(spot * 0.4 * iv * np.sqrt(t), spot * 0.01, 0.25))


def _conf_tier(raw: float) -> float:
    """LSE half-Kelly style: 0.35/0.35/0.65/1.0."""
    r = float(raw)
    if r <= 0:
        return 0.0
    if r < 0.55:
        return 0.35
    if r < 0.65:
        return 0.35
    if r < 0.78:
        return 0.65
    return 1.0


def _volume_surge_check(df: pd.DataFrame, vol_surge_mult: float = 1.25) -> pd.Series:
    """BREAKOUT_PRECIPITANTS: require volume surge for real breakouts."""
    vol = df["volume"]
    vol_sma = vol.rolling(20, min_periods=10).mean()
    rvol = vol / vol_sma
    vol_expand = vol > vol_sma
    vol_rising = vol > vol.shift(5)
    return (rvol >= vol_surge_mult) | (vol_expand & vol_rising)


def _prep_structure(df: pd.DataFrame) -> pd.DataFrame:
    """Add EMA200 + realized vol for adaptive DTE."""
    px = df[["close"]].copy()
    px.index = pd.to_datetime(px.index)
    if getattr(px.index, "tz", None) is not None:
        px.index = px.index.tz_localize(None)
    px = px.resample("1D").last().dropna()
    px["sma200"] = px["close"].rolling(200, min_periods=100).mean()
    ret = px["close"].pct_change()
    px["rv20"] = ret.rolling(20, min_periods=15).std() * np.sqrt(252)
    px["rv_percentile"] = px["rv20"].rolling(252, min_periods=60).apply(
        lambda s: s.rank(pct=True).iloc[-1], raw=False
    )
    return px


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
        self.initial_cash = float(cfg.get("initial_cash", 1_000_000.0))
        self.risk_pct = float(cfg.get("risk_pct", 0.10))
        self.dte_days = int(cfg.get("dte_days", 14))
        self.dte_high_vol = int(cfg.get("dte_high_vol", 10))
        self.dte_low_vol = int(cfg.get("dte_low_vol", 21))
        self.otm_pct = float(cfg.get("otm_pct", 0.0))
        self.contract_mult = int(cfg.get("contract_multiplier", 100))
        self.halt_dd = float(cfg.get("halt_dd", 0.28))
        self.flatten_dd = float(cfg.get("flatten_dd", 0.42))
        self.max_contracts = int(cfg.get("max_contracts", 500))
        self.use_narrative = bool(cfg.get("use_narrative", True))
        self.narrative_mode = str(cfg.get("narrative_mode", "surgical"))
        self.use_conf_tier = bool(cfg.get("use_conf_tier", True))
        self.loss_cooloff_days = int(cfg.get("loss_cooloff_days", 10))
        self.volume_surge_mult = float(cfg.get("volume_surge_mult", 1.35))
        self.vol_regime_high = float(cfg.get("vol_regime_high", 0.75))
        self.use_ema200_regime = bool(cfg.get("use_ema200_regime", True))
        self._macro = None

    def _get_dte(self, rv_pct: float) -> int:
        if rv_pct > self.vol_regime_high:
            return self.dte_high_vol
        return self.dte_low_vol

    def _ensure_macro(self, start: str, end: str) -> None:
        if self._macro is not None or not self.use_narrative:
            return
        try:
            self._macro = _load_macro(start, end)
        except Exception:
            self._macro = None

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        stock = self.equity_engine.generate(data_map)
        daily_sigs: Dict[str, pd.Series] = {}
        daily_px: Dict[str, pd.Series] = {}
        daily_structure: Dict[str, pd.DataFrame] = {}
        
        for code, sig in stock.items():
            if code not in data_map:
                continue
            daily_sigs[code] = _to_daily_signal(sig)
            daily_px[code] = _to_daily_close(data_map[code])
            daily_structure[code] = _prep_structure(data_map[code])

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
            ts_ts = pd.Timestamp(ts)

            # Update MTM
            for code, leg in list(open_legs.items()):
                if ts_ts not in daily_px[code].index:
                    continue
                spot = float(daily_px[code].loc[ts_ts])
                if np.isfinite(spot) and spot > 0:
                    leg["mtm"] = leg["qty"] * self.contract_mult * 0.5 * (spot - leg["entry_spot"])

            marked = equity + sum(l.get("mtm", 0.0) for l in open_legs.values())
            peak = max(peak, marked)
            dd = (peak - marked) / peak if peak > 0 else 0.0

            if dd >= self.flatten_dd and open_legs:
                for code, leg in list(open_legs.items()):
                    mtm = leg.get("mtm", 0.0)
                    if mtm < 0:
                        last_loss[code] = ts_ts
                    out.append({
                        "date": date_str, "action": "close", "underlying": code,
                        "legs": [{"type": "call", "strike": leg["strike"], 
                                  "expiry": leg["expiry"], "qty": leg["qty"]}],
                    })
                    equity = max(equity + mtm, equity * 0.01)
                    del open_legs[code]
                peak = max(peak, equity)
                continue

            narr_m = 1.0
            allow = True
            if self.use_narrative and self._macro is not None:
                feat = self._macro.features_on(ts_ts, mode=self.narrative_mode)
                narr_m = float(feat.get("size_mult", 1.0))
                allow = bool(feat.get("allow_entry", True))

            for code in daily_sigs:
                if ts_ts not in daily_sigs[code].index or ts_ts not in daily_px[code].index:
                    continue
                raw = float(daily_sigs[code].loc[ts_ts])
                spot = float(daily_px[code].loc[ts_ts])
                
                if not np.isfinite(spot) or spot <= 0:
                    continue
                    
                was = prev_sig[code]
                prev_sig[code] = raw
                entering = was <= 0 and raw > 0
                exiting = was > 0 and raw <= 0

                if exiting and code in open_legs:
                    leg = open_legs.pop(code)
                    mtm = leg.get("mtm", 0.0)
                    if mtm < 0:
                        last_loss[code] = ts_ts
                    out.append({"date": date_str, "action": "close", "underlying": code,
                               "legs": [{"type": "call", "strike": leg["strike"], 
                                       "expiry": leg["expiry"], "qty": leg["qty"]}],
                              })
                    equity = max(equity + mtm, equity * 0.01)
                    peak = max(peak, equity)
                    continue

                if entering and code not in open_legs:
                    if dd >= self.halt_dd or not allow:
                        continue
                    if self.loss_cooloff_days > 0 and code in last_loss:
                        days_since = (ts_ts - last_loss[code]).days
                        if days_since < self.loss_cooloff_days:
                            continue
                    
                    # EMA200 regime filter (soft - reduce size if below)
                    sma200 = float(daily_structure[code].loc[ts_ts].get("sma200", np.nan))
                    ema200_mult = 1.0
                    if self.use_ema200_regime and np.isfinite(sma200):
                        if spot < sma200 * 0.95:
                            ema200_mult = 0.0  # Skip if below 200 SMA
                        elif spot < sma200:
                            ema200_mult = 0.5  # Reduce size if below but near
                    
                    if ema200_mult == 0.0:
                        continue

                    # Volume surge filter (soft - reduce size if no surge)
                    vol_surge = _volume_surge_check(data_map[code], self.volume_surge_mult)
                    vol_surge_daily = vol_surge.resample("1D").last().fillna(False)
                    vol_surge_check = vol_surge_daily.reindex(daily_px[code].index, fill_value=False)
                    vs_mult = 1.0 if (ts_ts in vol_surge_check.index and bool(vol_surge_check.loc[ts_ts])) else 0.5

                    conf_m = _conf_tier(raw) if self.use_conf_tier else min(float(raw), 1.0)
                    if conf_m <= 0:
                        continue
                    size_frac = conf_m * narr_m * vs_mult * ema200_mult
                    if size_frac <= 0.05:
                        continue

                    rv_pct = float(daily_structure[code].loc[ts_ts].get("rv_percentile", 0.5))
                    prem = _est_atm_premium(spot)
                    dte = self._get_dte(rv_pct)
                    budget = max(equity * self.risk_pct * size_frac, 0.0)
                    qty = int(budget / (prem * self.contract_mult))
                    qty = int(np.clip(qty, 0, self.max_contracts))
                    if qty < 1:
                        continue

                    expiry = (ts_ts + pd.Timedelta(days=dte)).strftime("%Y-%m-%d")
                    strike = float(round(spot * (1.0 + self.otm_pct)))
                    out.append({
                        "date": date_str, "action": "open", "underlying": code,
                        "legs": [{"type": "call", "strike": strike, 
                                  "expiry": expiry, "qty": qty}],
                    })
                    open_legs[code] = {
                        "strike": strike, "expiry": expiry, "qty": qty,
                        "entry_spot": spot, "mtm": 0.0,
                    }
                    equity -= qty * prem * self.contract_mult
                    equity = max(equity, self.initial_cash * 0.01)

        return out