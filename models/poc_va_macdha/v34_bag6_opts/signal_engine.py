"""v29_coldstart_opts — OOS/cold-start optimized options book.

Built to beat v22_opts_live on pure holdout folds (not full-window path games).

Rules from FINDINGS + autopsy:
  - Keep v22 DNA: 21 DTE ATM, continuous size, no conf-tier.
  - Surgical only: block fomc_day ∧ vix_elevated (fail-open if macro dies).
  - Short 5d cooloff after ticker loss (not 10d over-block).
  - After 2 consecutive book losses → half size next entry.
  - Premium estimate uses actual dte_days (v22 used implicit 30d).
  - No broad narrative / CPI gates / conf ladders.

AST-sandbox safe.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    spec = importlib.util.spec_from_file_location("v21_equity_se_v29", path)
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


def _to_daily_close(df: pd.DataFrame) -> pd.Series:
    d = df.copy()
    d.index = pd.to_datetime(d.index)
    if getattr(d.index, "tz", None) is not None:
        d.index = d.index.tz_localize(None)
    return d["close"].resample("1D").last().dropna()


def _est_atm_premium(spot: float, iv: float = 0.55, dte: float = 21.0) -> float:
    t = max(dte, 1.0) / 365.0
    return float(max(spot * 0.4 * iv * np.sqrt(t), spot * 0.01, 0.25))


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
        self.dte_days = int(cfg.get("dte_days", 21))
        self.otm_pct = float(cfg.get("otm_pct", 0.0))
        self.contract_mult = int(cfg.get("contract_multiplier", 100))
        self.halt_dd = float(cfg.get("halt_dd", 0.30))
        self.flatten_dd = float(cfg.get("flatten_dd", 0.45))
        self.max_contracts = int(cfg.get("max_contracts", 500))
        self.use_narrative = bool(cfg.get("use_narrative", True))
        self.narrative_mode = str(cfg.get("narrative_mode", "surgical"))
        self.loss_cooloff_days = int(cfg.get("loss_cooloff_days", 5))
        self.streak_losses_for_cut = int(cfg.get("streak_losses_for_cut", 2))
        self.streak_size_mult = float(cfg.get("streak_size_mult", 0.5))
        self.min_size_frac = float(cfg.get("min_size_frac", 0.35))
        self.max_size_frac = float(cfg.get("max_size_frac", 1.0))
        self._macro = None

    def _ensure_macro(self, start: str, end: str) -> None:
        if self._macro is not None or not self.use_narrative:
            return
        try:
            self._macro = _load_macro(start, end)
        except Exception:  # noqa: BLE001
            self._macro = None  # fail-open

    def _narrative_allow(self, ts: pd.Timestamp) -> tuple[bool, float]:
        """Return (allow_entry, size_mult). Fail-open on any error."""
        if not self.use_narrative or self._macro is None:
            return True, 1.0
        try:
            feat = self._macro.features_on(ts, mode=self.narrative_mode)
            allow = bool(feat.get("allow_entry", True))
            sm = float(feat.get("size_mult", 1.0))
            if not np.isfinite(sm):
                sm = 1.0
            return allow, float(np.clip(sm, 0.0, 1.0))
        except Exception:  # noqa: BLE001
            return True, 1.0

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        stock = self.equity_engine.generate(data_map)
        daily_sigs: Dict[str, pd.Series] = {}
        daily_px: Dict[str, pd.Series] = {}
        for code, sig in stock.items():
            if code not in data_map:
                continue
            daily_sigs[code] = _to_daily_signal(sig)
            daily_px[code] = _to_daily_close(data_map[code])

        if not daily_sigs:
            return []

        idx = sorted(set().union(*[set(s.index) for s in daily_sigs.values()]))
        if idx and self.use_narrative:
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
        consec_losses = 0  # book-level closed-trade loss streak

        for ts in idx:
            date_str = str(pd.Timestamp(ts).date())
            ts = pd.Timestamp(ts)

            for code, leg in list(open_legs.items()):
                if ts not in daily_px[code].index:
                    continue
                spot = float(daily_px[code].loc[ts])
                if not np.isfinite(spot) or spot <= 0:
                    continue
                # same crude mark as v22 (consistent with engine family)
                leg["mtm"] = leg["qty"] * self.contract_mult * 0.5 * (spot - leg["entry_spot"])

            marked = equity + sum(l.get("mtm", 0.0) for l in open_legs.values())
            peak = max(peak, marked)
            dd = (peak - marked) / peak if peak > 0 else 0.0

            if dd >= self.flatten_dd and open_legs:
                for code, leg in list(open_legs.items()):
                    mtm = float(leg.get("mtm", 0.0))
                    if mtm < 0:
                        last_loss[code] = ts
                        consec_losses += 1
                    else:
                        consec_losses = 0
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

            allow, narr_m = self._narrative_allow(ts)

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
                    mtm = float(leg.get("mtm", 0.0))
                    if mtm < 0:
                        last_loss[code] = ts
                        consec_losses += 1
                    else:
                        consec_losses = 0
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
                    # short cooloff after ticker loss
                    if self.loss_cooloff_days > 0 and code in last_loss:
                        if (ts - last_loss[code]).days < self.loss_cooloff_days:
                            continue
                    # continuous size like v22; skip weak signals (quality floor)
                    # rather than boosting them to min (boosting hurt capacity/risk).
                    if raw < self.min_size_frac:
                        continue
                    size_frac = float(np.clip(raw, 0.0, self.max_size_frac))
                    size_frac *= narr_m
                    if consec_losses >= self.streak_losses_for_cut:
                        size_frac *= self.streak_size_mult
                    if size_frac <= 0.05:
                        continue
                    prem = _est_atm_premium(spot, dte=float(self.dte_days))
                    budget = max(equity * self.risk_pct * size_frac, 0.0)
                    qty = int(budget / (prem * self.contract_mult))
                    qty = int(np.clip(qty, 0, self.max_contracts))
                    if qty < 1:
                        continue
                    expiry = (ts + pd.Timedelta(days=self.dte_days)).strftime("%Y-%m-%d")
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
