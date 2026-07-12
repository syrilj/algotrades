"""v22_robust — live-trading robust long-call options strategy.

Enhancements over v22_opts_live:
  - trend filter (price > 50-day SMA) to avoid buying calls in downtrends
  - volatility filter (20d realized vol below threshold)
  - stock-level stop loss / profit target on open legs
  - tighter drawdown halt/flatten
  - smaller risk-per-trade and max position caps

Callers: backtest.runner → run_options_backtest when config engine=options.
"""

from __future__ import annotations

import importlib.util
import json
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
    spec = importlib.util.spec_from_file_location("v21_equity_se", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod.SignalEngine()


def _to_daily_signal(sig: pd.Series) -> pd.Series:
    s = sig.copy()
    s.index = pd.to_datetime(s.index)
    if getattr(s.index, "tz", None) is not None:
        s.index = s.index.tz_localize(None)
    return s.resample("1D").last().dropna()


def _est_atm_premium(spot: float, iv: float = 0.55, dte: float = 30.0) -> float:
    """Rough ATM premium ≈ 0.4 * S * iv * sqrt(T) (Brenner-Subrahmanyam-ish)."""
    t = max(dte, 1.0) / 365.0
    return float(max(spot * 0.4 * iv * np.sqrt(t), spot * 0.01, 0.25))


def _prep_px(df: pd.DataFrame) -> pd.DataFrame:
    """Add robustness filters: SMA, realized vol, vol percentile."""
    px = df[["close", "high", "low", "volume"]].copy()
    px.index = pd.to_datetime(px.index)
    if getattr(px.index, "tz", None) is not None:
        px.index = px.index.tz_localize(None)
    px = px.resample("1D").last().dropna()
    px["sma50"] = px["close"].rolling(50, min_periods=30).mean()
    ret = px["close"].pct_change()
    px["rv20"] = ret.rolling(20, min_periods=15).std() * np.sqrt(252)
    px["rv_percentile"] = px["rv20"].rolling(252, min_periods=60).apply(
        lambda s: s.rank(pct=True).iloc[-1], raw=False
    )
    return px


class SignalEngine:
    """OptionsSignalEngine API: generate() → list of trade instructions."""

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
        self.risk_pct = float(cfg.get("risk_pct", 0.03))
        self.dte_days = int(cfg.get("dte_days", 21))
        self.otm_pct = float(cfg.get("otm_pct", 0.0))
        self.contract_mult = int(cfg.get("contract_multiplier", 100))
        self.halt_dd = float(cfg.get("halt_dd", 0.15))
        self.flatten_dd = float(cfg.get("flatten_dd", 0.25))
        self.max_contracts = int(cfg.get("max_contracts", 100))
        self.require_uptrend = bool(cfg.get("require_uptrend", True))
        self.require_low_vol = bool(cfg.get("require_low_vol", True))
        self.vol_percentile_max = float(cfg.get("vol_percentile_max", 0.70))
        self.stock_stop_pct = float(cfg.get("stock_stop_pct", -0.05))
        self.stock_tp_pct = float(cfg.get("stock_tp_pct", 0.10))
        self.max_position_pct = float(cfg.get("max_position_pct", 0.15))

    def _allowed_entry(self, ts: pd.Timestamp, spot: float, df: pd.DataFrame) -> bool:
        if ts not in df.index:
            return False
        row = df.loc[ts]
        sma50 = row.get("sma50")
        rv_pct = row.get("rv_percentile")
        if self.require_uptrend and (not np.isfinite(sma50) or spot < sma50):
            return False
        if self.require_low_vol and (not np.isfinite(rv_pct) or rv_pct > self.vol_percentile_max):
            return False
        return True

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        stock = self.equity_engine.generate(data_map)
        daily_sigs: Dict[str, pd.Series] = {}
        daily_px: Dict[str, pd.DataFrame] = {}
        for code, sig in stock.items():
            if code not in data_map:
                continue
            daily_sigs[code] = _to_daily_signal(sig)
            daily_px[code] = _prep_px(data_map[code])

        if not daily_sigs:
            return []

        idx = sorted(set().union(*[set(s.index) for s in daily_sigs.values()]))
        equity = float(self.initial_cash)
        peak = equity
        open_legs: Dict[str, Dict[str, Any]] = {}
        out: List[Dict[str, Any]] = []
        prev_sig = {c: 0.0 for c in daily_sigs}

        for ts in idx:
            date_str = str(pd.Timestamp(ts).date())
            for code, leg in list(open_legs.items()):
                if ts not in daily_px[code].index:
                    continue
                spot = float(daily_px[code].loc[ts, "close"])
                if not np.isfinite(spot) or spot <= 0:
                    continue
                leg["mtm"] = leg["qty"] * self.contract_mult * 0.5 * (spot - leg["entry_spot"])

                ret_from_entry = (spot / leg["entry_spot"]) - 1.0 if leg["entry_spot"] > 0 else 0.0
                if ret_from_entry <= self.stock_stop_pct or ret_from_entry >= self.stock_tp_pct:
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
                    equity = max(equity + leg.get("mtm", 0.0), equity * 0.01)
                    del open_legs[code]

            marked = equity + sum(l.get("mtm", 0.0) for l in open_legs.values())
            peak = max(peak, marked)
            dd = (peak - marked) / peak if peak > 0 else 0.0

            if dd >= self.flatten_dd and open_legs:
                for code, leg in list(open_legs.items()):
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
                    equity = max(equity + leg.get("mtm", 0.0), equity * 0.01)
                    del open_legs[code]
                peak = max(peak, equity)
                continue

            for code in daily_sigs:
                if ts not in daily_sigs[code].index or ts not in daily_px[code].index:
                    continue
                raw = float(daily_sigs[code].loc[ts])
                spot = float(daily_px[code].loc[ts, "close"])
                if not np.isfinite(spot) or spot <= 0:
                    continue
                was = prev_sig[code]
                prev_sig[code] = raw

                entering = was <= 0 and raw > 0
                exiting = was > 0 and raw <= 0

                if exiting and code in open_legs:
                    leg = open_legs.pop(code)
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
                    equity = max(equity + leg.get("mtm", 0.0), equity * 0.01)
                    peak = max(peak, equity)
                    continue

                if entering and code not in open_legs:
                    if dd >= self.halt_dd:
                        continue
                    if not self._allowed_entry(ts, spot, daily_px[code]):
                        continue
                    prem = _est_atm_premium(spot)
                    position_budget = equity * self.max_position_pct
                    trade_budget = equity * self.risk_pct * float(raw)
                    budget = min(position_budget, trade_budget)
                    budget = max(budget, 0.0)
                    qty = int(budget / (prem * self.contract_mult))
                    qty = int(np.clip(qty, 0, self.max_contracts))
                    if qty < 1:
                        continue
                    expiry = (pd.Timestamp(ts) + pd.Timedelta(days=self.dte_days)).strftime(
                        "%Y-%m-%d"
                    )
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
