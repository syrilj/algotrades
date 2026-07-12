"""v24_compound — full-account compounding ATM calls on v21 equity signals.

Converts v21 equity signals into options instructions for the backtest options
engine. Uses the same 30-day historical-vol estimate the options engine uses for
pricing, so the virtual equity tracker tracks option value instead of a half-delta
spot approximation. The goal is to keep the full account deployed and compound
wins into the next signal while avoiding near-total losses.

API: SignalEngine.generate(data_map) -> list[{date, action, underlying, legs}].
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

# Load the BS helper from the repo tools
import math

from scipy.stats import norm


def _bs_price(S: float, K: float, T: float, r: float, sigma: float, call: bool = True) -> float:
    if S <= 0 or K <= 0 or sigma <= 0:
        return max(S - K, 0.0) if call else max(K - S, 0.0)
    if T <= 1e-8:
        return max(S - K, 0.0) if call else max(K - S, 0.0)
    sqrtT = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrtT)
    d2 = d1 - sigma * sqrtT
    if call:
        return float(S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2))
    return float(K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))


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
    spec = importlib.util.spec_from_file_location("v21_equity_se_v24", path)
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


def _iv(close: pd.Series, ts: pd.Timestamp, window: int = 30) -> float:
    log_ret = np.log(close / close.shift(1))
    hv = log_ret.rolling(window=window).std() * np.sqrt(252)
    v = hv.loc[:ts]
    if not v.dropna().empty:
        return float(np.clip(v.dropna().iloc[-1], 0.05, 1.5))
    return 0.5


def _iv_adj(S: float, K: float, base_iv: float, skew: float = 0.15, curvature: float = 0.05) -> float:
    if S <= 0 or K <= 0:
        return max(base_iv, 0.01)
    log_moneyness = np.log(K / S)
    adj = base_iv - skew * log_moneyness + curvature * log_moneyness ** 2
    return max(float(adj), 0.01)


def _size_mult(history: List[float]) -> float:
    return 1.0

class SignalEngine:
    """OptionsSignalEngine API: generate() -> list of trade instructions."""

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
        self.initial_cash = float(cfg.get("initial_cash", 10_000.0))
        self.risk_pct = float(cfg.get("risk_pct", 1.0))
        self.dte_days = int(cfg.get("dte_days", 21))
        self.otm_pct = float(cfg.get("otm_pct", 0.0))
        self.contract_mult = int(cfg.get("contract_multiplier", 100))
        self.halt_dd = float(cfg.get("halt_dd", 0.99))
        self.flatten_dd = float(cfg.get("flatten_dd", 0.99))
        self.max_contracts = int(cfg.get("max_contracts", 5000))
        self.risk_free = float(cfg.get("risk_free", 0.05))
        self.commission = float(cfg.get("commission", 0.001))
        self._history = []
        self._prev_positions = {}
        self._entered = {}

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        stock = self.equity_engine.generate(data_map)
        daily_sigs: Dict[str, pd.Series] = {}
        daily_px: Dict[str, pd.Series] = {}
        for code, sig in stock.items():
            if code not in data_map:
                continue
            daily_sigs[code] = _to_daily_signal(sig)
            px = data_map[code]["close"].copy()
            px.index = pd.to_datetime(px.index)
            if getattr(px.index, "tz", None) is not None:
                px.index = px.index.tz_localize(None)
            daily_px[code] = px.resample("1D").last().dropna()

        if not daily_sigs:
            return []

        idx = sorted(set().union(*[set(s.index) for s in daily_sigs.values()]))
        cash = float(self.initial_cash)
        equity = float(self.initial_cash)
        peak = equity
        open_legs: Dict[str, Dict[str, Any]] = {}
        out: List[Dict[str, Any]] = []
        prev_sig = {c: 0.0 for c in daily_sigs}

        for ts in idx:
            date_str = str(pd.Timestamp(ts).date())

            # mark open leg to current option value
            if open_legs:
                code = list(open_legs.keys())[0]
                leg = open_legs[code]
                if ts in daily_px[code].index:
                    spot = float(daily_px[code].loc[ts])
                    if np.isfinite(spot) and spot > 0:
                        close = data_map[code]["close"]
                        sigma = _iv_adj(spot, leg["strike"], _iv(close, ts))
                        T = max((pd.Timestamp(leg["expiry"]) - pd.Timestamp(ts)).days, 0) / 365.0
                        prem = _bs_price(spot, leg["strike"], T, self.risk_free, sigma, True)
                        leg["mtm"] = leg["qty"] * self.contract_mult * prem

            marked = cash + sum(l.get("mtm", 0.0) for l in open_legs.values())
            peak = max(peak, marked)
            dd = (peak - marked) / peak if peak > 0 else 0.0

            if dd >= self.flatten_dd and open_legs:
                code, leg = list(open_legs.items())[0]
                out.append({
                    "date": date_str,
                    "action": "close",
                    "underlying": code,
                    "legs": [{"type": "call", "strike": leg["strike"], "expiry": leg["expiry"], "qty": leg["qty"]}],
                })
                cash = max(cash + leg.get("mtm", 0.0), self.initial_cash * 0.01)
                equity = cash
                open_legs.clear()
                peak = max(peak, equity)
                continue

            # first process any close for the single open leg
            if open_legs:
                code = list(open_legs.keys())[0]
                raw = float(daily_sigs[code].loc[ts])
                was = prev_sig[code]
                prev_sig[code] = raw
                exiting = was > 0 and raw <= 0
                if exiting:
                    leg = open_legs.pop(code)
                    out.append({
                        "date": date_str,
                        "action": "close",
                        "underlying": code,
                        "legs": [{"type": "call", "strike": leg["strike"], "expiry": leg["expiry"], "qty": leg["qty"]}],
                    })
                    cash = max(cash + leg.get("mtm", 0.0), self.initial_cash * 0.01)
                    equity = cash
                    peak = max(peak, equity)

            # if no open leg, collect all entry signals and pick the highest raw
            if not open_legs and dd < self.halt_dd:
                candidates = []
                for code in daily_sigs:
                    if ts not in daily_sigs[code].index or ts not in daily_px[code].index:
                        continue
                    raw = float(daily_sigs[code].loc[ts])
                    was = prev_sig[code]
                    prev_sig[code] = raw
                    entering = was <= 0 and raw > 0
                    if entering:
                        spot = float(daily_px[code].loc[ts])
                        if np.isfinite(spot) and spot > 0:
                            candidates.append((raw, code, spot))

                if candidates:
                    # pick the highest-confidence candidate
                    candidates.sort(key=lambda x: x[0], reverse=True)
                    raw, code, spot = candidates[0]
                    close = data_map[code]["close"]
                    base_iv = _iv(close, ts)
                    T0 = self.dte_days / 365.0
                    expiry = (pd.Timestamp(ts) + pd.Timedelta(days=self.dte_days)).strftime("%Y-%m-%d")
                    strike = float(round(spot * (1.0 + self.otm_pct)))
                    sigma = _iv_adj(spot, strike, base_iv)
                    prem_entry = _bs_price(spot, strike, T0, self.risk_free, sigma, True)
                    if prem_entry > 0:
                        # Full-account compound: size by signal strength.
                        budget = cash * self.risk_pct * float(raw)
                        qty = int(budget / (prem_entry * self.contract_mult))
                        qty = int(np.clip(qty, 0, self.max_contracts))
                        if qty >= 1:
                            cost = qty * prem_entry * self.contract_mult
                            out.append({
                                "date": date_str,
                                "action": "open",
                                "underlying": code,
                                "legs": [{"type": "call", "strike": strike, "expiry": expiry, "qty": qty}],
                            })
                            open_legs[code] = {
                                "strike": strike,
                                "expiry": expiry,
                                "qty": qty,
                                "entry_prem": prem_entry,
                                "entry_spot": spot,
                                "cost": cost,
                                "mtm": 0.0,
                            }
                            cash -= cost
                            equity = cash + cost

        return out

    def _precompute(self, data_map: Dict[str, pd.DataFrame]) -> None:
        if getattr(self, "_daily_sigs", None) is not None:
            return
        stock = self.equity_engine.generate(data_map)
        self._daily_sigs: Dict[str, pd.Series] = {}
        self._daily_px: Dict[str, pd.Series] = {}
        for code, sig in stock.items():
            if code not in data_map:
                continue
            self._daily_sigs[code] = _to_daily_signal(sig)
            px = data_map[code]["close"].copy()
            px.index = pd.to_datetime(px.index)
            if getattr(px.index, "tz", None) is not None:
                px.index = px.index.tz_localize(None)
            self._daily_px[code] = px.resample("1D").last().dropna()
        self._idx = sorted(set().union(*[set(s.index) for s in self._daily_sigs.values()])) if self._daily_sigs else []
        self._prev_sig = {c: 0.0 for c in self._daily_sigs}
        self._peak = float(self.initial_cash)

    def generate_day(self, data_map: Dict[str, pd.DataFrame], state: Dict[str, Any], ts) -> List[Dict[str, Any]]:
        """Stateful per-day signal generator with single-position compounding and re-entry."""
        self._precompute(data_map)
        ts = pd.Timestamp(ts)
        if ts not in self._idx:
            return []
        date_str = str(ts.date())

        cash = float(state.get("cash", self.initial_cash))
        portfolio_value = float(state.get("portfolio_value", cash))
        positions = state.get("positions", []) or []
        open_positions = {p["code"]: dict(p) for p in positions if p.get("code") and p.get("qty", 0)}
        open_codes = set(open_positions.keys())

        # Recognize positions closed/exercised since the previous day and update history
        prev_positions = getattr(self, "_prev_positions", {})
        for code in set(prev_positions.keys()) - open_codes:
            prev = prev_positions[code]
            close = data_map[code]["close"]
            before = close.loc[:ts]
            spot = float(before.iloc[-1]) if not before.empty else 0.0
            if not np.isfinite(spot) or spot <= 0:
                continue
            base_iv = _iv(close, ts)
            sigma = _iv_adj(spot, prev["strike"], base_iv)
            T = max((pd.Timestamp(prev["expiry"]) - ts).days, 0) / 365.0
            mark = _bs_price(spot, prev["strike"], T, self.risk_free, sigma, prev.get("option_type", "call") == "call")
            self._history.append((mark - prev["entry_price"]) * prev["qty"] * self.contract_mult)

        # Current state becomes the previous state for next call
        self._prev_positions = open_positions

        # High-water mark and drawdown
        self._peak = max(getattr(self, "_peak", self.initial_cash), portfolio_value)
        dd = (self._peak - portfolio_value) / self._peak if self._peak > 0 else 0.0

        out: List[Dict[str, Any]] = []
        cash_after_close = cash

        # Flatten on catastrophic drawdown
        if dd >= self.flatten_dd and open_codes:
            for code in list(open_codes):
                pos = open_positions[code]
                out.append({
                    "date": date_str,
                    "action": "close",
                    "underlying": code,
                    "legs": [{"type": pos.get("option_type", "call"), "strike": pos["strike"], "expiry": pos["expiry"], "qty": pos["qty"]}],
                })
                close = data_map[code]["close"]
                before = close.loc[:ts]
                spot = float(before.iloc[-1]) if not before.empty else 0.0
                if np.isfinite(spot) and spot > 0:
                    base_iv = _iv(close, ts)
                    sigma = _iv_adj(spot, pos["strike"], base_iv)
                    T = max((pd.Timestamp(pos["expiry"]) - ts).days, 0) / 365.0
                    mark = _bs_price(spot, pos["strike"], T, self.risk_free, sigma, pos.get("option_type", "call") == "call")
                    cash_after_close += mark * pos["qty"] * self.contract_mult * (1.0 - self.commission)
                del open_positions[code]
            open_codes.clear()

        # Close on signal reversal
        for code in list(open_codes):
            sig = self._daily_sigs[code]
            was = self._prev_sig.get(code, 0.0)
            raw = float(sig.loc[ts]) if ts in sig.index else was
            if ts in sig.index:
                self._prev_sig[code] = raw
            exiting = was > 0 and raw <= 0
            if raw <= 0:
                self._entered[code] = False
            if exiting:
                pos = open_positions[code]
                out.append({
                    "date": date_str,
                    "action": "close",
                    "underlying": code,
                    "legs": [{"type": pos.get("option_type", "call"), "strike": pos["strike"], "expiry": pos["expiry"], "qty": pos["qty"]}],
                })
                close = data_map[code]["close"]
                before = close.loc[:ts]
                spot = float(before.iloc[-1]) if not before.empty else 0.0
                if np.isfinite(spot) and spot > 0:
                    base_iv = _iv(close, ts)
                    sigma = _iv_adj(spot, pos["strike"], base_iv)
                    T = max((pd.Timestamp(pos["expiry"]) - ts).days, 0) / 365.0
                    mark = _bs_price(spot, pos["strike"], T, self.risk_free, sigma, pos.get("option_type", "call") == "call")
                    self._history.append((mark - pos["entry_price"]) * pos["qty"] * self.contract_mult)
                    cash_after_close += mark * pos["qty"] * self.contract_mult * (1.0 - self.commission)
                open_codes.discard(code)
                del open_positions[code]

        # New entries: single best candidate, sized by raw confidence and available cash
        if dd < self.halt_dd and not open_codes and cash_after_close > 0:
            candidates = []
            for code in self._daily_sigs:
                if ts not in self._daily_sigs[code].index or ts not in self._daily_px[code].index:
                    continue
                raw = float(self._daily_sigs[code].loc[ts])
                was = self._prev_sig.get(code, 0.0)
                self._prev_sig[code] = raw
                entering = raw > 0 and not self._entered.get(code, False)
                if entering:
                    spot = float(self._daily_px[code].loc[ts])
                    if np.isfinite(spot) and spot > 0:
                        candidates.append((raw, code, spot))

            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                for raw, code, spot in candidates:
                    if cash_after_close <= 0:
                        break
                    close = data_map[code]["close"]
                    base_iv = _iv(close, ts)
                    expiry = (pd.Timestamp(ts) + pd.Timedelta(days=self.dte_days)).strftime("%Y-%m-%d")
                    strike = float(round(spot * (1.0 + self.otm_pct)))
                    sigma = _iv_adj(spot, strike, base_iv)
                    T0 = max(self.dte_days, 1) / 365.0
                    prem_entry = _bs_price(spot, strike, T0, self.risk_free, sigma, True)
                    if prem_entry <= 0:
                        continue
                    budget = cash_after_close * self.risk_pct * float(raw) / (1.0 + self.commission)
                    qty = int(budget / (prem_entry * self.contract_mult))
                    qty = int(np.clip(qty, 0, self.max_contracts))
                    if qty < 1:
                        continue
                    out.append({
                        "date": date_str,
                        "action": "open",
                        "underlying": code,
                        "legs": [{"type": "call", "strike": strike, "expiry": expiry, "qty": qty}],
                    })
                    cost = prem_entry * qty * self.contract_mult * (1.0 + self.commission)
                    cash_after_close -= cost
                    open_positions[code] = {
                        "code": code,
                        "option_type": "call",
                        "strike": strike,
                        "expiry": expiry,
                        "qty": qty,
                        "entry_price": prem_entry,
                    }
                    open_codes.add(code)
                    self._entered[code] = True
                    break

        self._prev_positions = open_positions
        return out
