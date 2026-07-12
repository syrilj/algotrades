"""v21_mstr_tsla_opts — long ATM calls on MSTR/TSLA entries.

Converts v21 equity signals into options instructions for the backtest
options engine. Compounds size from a virtual equity tracker. Allows more
risk than stock sleeve, with account DD floor (halt / flatten).

Callers: backtest.runner → run_options_backtest when config engine=options;
run dir runs/poc_va_v21_mstr_tsla_opts/code/signal_engine.py (copy).
API: SignalEngine.generate(data_map) -> list[{date, action, underlying, legs}].
Leg schema: {type, strike, expiry YYYY-MM-DD, qty}.
User: trade MSTR/TSLA, compound profits, options with more risk without blowing account.
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
        here.parents[1] / "v21_mstr_tsla" / "signal_engine.py",  # models/.../v21_mstr_tsla_opts/
        here.parents[3] / "models" / "poc_va_macdha" / "v21_mstr_tsla" / "signal_engine.py",  # runs/.../code/
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
        self.risk_pct = float(cfg.get("risk_pct", 0.05))
        self.dte_days = int(cfg.get("dte_days", 30))
        self.otm_pct = float(cfg.get("otm_pct", 0.0))
        self.contract_mult = int(cfg.get("contract_multiplier", 100))
        self.halt_dd = float(cfg.get("halt_dd", 0.25))
        self.flatten_dd = float(cfg.get("flatten_dd", 0.40))
        self.max_contracts = int(cfg.get("max_contracts", 500))

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
                spot = float(daily_px[code].loc[ts])
                if not np.isfinite(spot) or spot <= 0:
                    continue
                leg["mtm"] = leg["qty"] * self.contract_mult * 0.5 * (spot - leg["entry_spot"])

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
                spot = float(daily_px[code].loc[ts])
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
                    prem = _est_atm_premium(spot)
                    budget = max(equity * self.risk_pct * float(raw), 0.0)
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
