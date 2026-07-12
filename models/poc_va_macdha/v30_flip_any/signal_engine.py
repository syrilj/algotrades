"""v30_flip_any — Coulling VPA call/put flips on ANY stock.

Volume = effort, price = result (Anna Coulling VPA).
Calls after stopping/no-supply/spring; puts after topping/no-demand/upthrust.
Short hold, long call OR put only, aggressive size, any universe.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import numpy as np
import pandas as pd


def _load_vpa():
    """Load vpa.py next to this engine (works from models/ or runs/*/code/)."""
    here = Path(__file__).resolve().parent
    candidates = [
        here / "vpa.py",
        here.parents[0] / "vpa.py",
        Path("/Users/syriljacob/Desktop/TradingAlgoWork/models/poc_va_macdha/v30_flip_any/vpa.py"),
    ]
    # also search upward for models path
    for p in here.parents:
        c = p / "models" / "poc_va_macdha" / "v30_flip_any" / "vpa.py"
        if c.exists():
            candidates.append(c)
            break
    for p in candidates:
        if p.exists():
            spec = importlib.util.spec_from_file_location("v30_vpa", p)
            mod = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(mod)
            return mod
    raise FileNotFoundError(f"vpa.py not found; tried {candidates}")


def _to_daily(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d.index = pd.to_datetime(d.index)
    if getattr(d.index, "tz", None) is not None:
        d.index = d.index.tz_localize(None)
    o = d["open"].resample("1D").first()
    h = d["high"].resample("1D").max()
    l = d["low"].resample("1D").min()
    c = d["close"].resample("1D").last()
    v = d["volume"].resample("1D").sum() if "volume" in d.columns else c * 0 + 1.0
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v}).dropna()


def _est_prem(spot: float, dte: float = 7.0, iv: float = 0.55) -> float:
    t = max(dte, 1.0) / 365.0
    return float(max(spot * 0.4 * iv * np.sqrt(t), spot * 0.008, 0.15))


def _norm_code(c: str) -> str:
    return str(c).strip().upper()


class SignalEngine:
    def __init__(self):
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
        self.risk_pct = float(cfg.get("risk_pct", 0.70))
        self.dte_days = int(cfg.get("dte_days", 7))
        self.otm_pct = float(cfg.get("otm_pct", 0.0))
        self.max_hold_days = int(cfg.get("max_hold_days", 5))
        self.quick_target_pct = float(cfg.get("quick_target_pct", 0.03))
        self.cut_pct = float(cfg.get("cut_pct", 0.05))
        self.contract_mult = int(cfg.get("contract_multiplier", 100))
        self.max_contracts = int(cfg.get("max_contracts", 500))
        self.max_open_positions = int(cfg.get("max_open_positions", 3))
        self.vpa_look = int(cfg.get("vpa_look", 5))
        self.vol_sma = int(cfg.get("vol_sma", 20))
        # standard | sniper (sniper = textbook VPA only, fewer trades)
        self.vpa_mode = str(cfg.get("vpa_mode", "standard")).lower()
        raw_codes = cfg.get("codes") or cfg.get("universe") or []
        self.allow_codes: Optional[Set[str]] = None
        if raw_codes:
            self.allow_codes = {_norm_code(x) for x in raw_codes}
        self._vpa = _load_vpa()

    def _allowed(self, code: str) -> bool:
        if self.allow_codes is None:
            return True
        c = _norm_code(code)
        if c in self.allow_codes:
            return True
        base = c.replace(".US", "")
        return base in self.allow_codes or f"{base}.US" in self.allow_codes

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        feats: Dict[str, pd.DataFrame] = {}
        for code, df in data_map.items():
            if not self._allowed(code):
                continue
            daily = _to_daily(df)
            if len(daily) < 30:
                continue
            feats[code] = self._vpa.vpa_frame(
                daily, look=self.vpa_look, vol_sma=self.vol_sma
            )
        if not feats:
            return []

        idx = sorted(set().union(*[set(f.index) for f in feats.values()]))
        equity = float(self.initial_cash)
        open_pos: Dict[str, Dict[str, Any]] = {}
        out: List[Dict[str, Any]] = []

        for ts in idx:
            ts = pd.Timestamp(ts)
            date_str = str(ts.date())

            for code in list(open_pos.keys()):
                if code not in feats or ts not in feats[code].index:
                    continue
                pos = open_pos[code]
                row = feats[code].loc[ts]
                spot = float(row["close"])
                held = (ts - pos["entry_ts"]).days
                entry = float(pos["entry_spot"])
                side = pos["type"]
                move = (spot - entry) / entry if entry > 0 else 0.0
                if side == "put":
                    move = -move
                dir_ = 1.0 if side == "call" else -1.0
                pos["mtm"] = pos["qty"] * self.contract_mult * 0.55 * dir_ * (spot - entry)

                exit_now = False
                if held >= self.max_hold_days:
                    exit_now = True
                if held >= 1 and move >= self.quick_target_pct:
                    exit_now = True
                if held >= 1 and move <= -self.cut_pct:
                    exit_now = True
                # VPA reverse: topping after long, stopping after short
                if side == "call" and (bool(row["put"]) or bool(row["topping_volume"]) or bool(row["no_demand"])):
                    if held >= 1:
                        exit_now = True
                if side == "put" and (bool(row["call"]) or bool(row["stopping_volume"]) or bool(row["no_supply"])):
                    if held >= 1:
                        exit_now = True
                if side == "call" and bool(row["red"]) and held >= 1:
                    exit_now = True
                if side == "put" and bool(row["green"]) and held >= 1:
                    exit_now = True

                if exit_now:
                    out.append(
                        {
                            "date": date_str,
                            "action": "close",
                            "underlying": code,
                            "legs": [
                                {
                                    "type": side,
                                    "strike": pos["strike"],
                                    "expiry": pos["expiry"],
                                    "qty": pos["qty"],
                                }
                            ],
                            "vpa_tag": self._vpa.tag_bar(row.to_dict()),
                        }
                    )
                    equity = max(equity + float(pos.get("mtm", 0.0)), self.initial_cash * 0.01)
                    del open_pos[code]

            if len(open_pos) >= self.max_open_positions:
                continue

            cands: List[tuple] = []
            for code, f in feats.items():
                if ts not in f.index or code in open_pos:
                    continue
                row = f.loc[ts]
                spot = float(row["close"])
                if not np.isfinite(spot) or spot <= 0:
                    continue
                want: Optional[str] = None
                if self.vpa_mode == "sniper":
                    if bool(row.get("call_sniper", False)):
                        want = "call"
                    elif bool(row.get("put_sniper", False)):
                        want = "put"
                else:
                    if bool(row["call"]):
                        want = "call"
                    elif bool(row["put"]):
                        want = "put"
                if want is None:
                    continue
                strength = float(row["strength"]) if np.isfinite(row["strength"]) else 0.0
                iv = float(row["iv"]) if np.isfinite(row["iv"]) else 0.55
                tag = self._vpa.tag_bar(row.to_dict())
                cands.append((strength, code, want, spot, iv, tag))

            cands.sort(key=lambda x: x[0], reverse=True)
            n_new = min(self.max_open_positions - len(open_pos), len(cands))
            if n_new <= 0:
                continue
            per_risk = self.risk_pct / float(n_new)

            for _str, code, want, spot, iv, tag in cands[:n_new]:
                if len(open_pos) >= self.max_open_positions:
                    break
                prem = _est_prem(spot, dte=float(self.dte_days), iv=iv)
                budget = max(equity * per_risk, 0.0)
                qty = int(budget / max(prem * self.contract_mult, 1e-9))
                qty = int(np.clip(qty, 0, self.max_contracts))
                if qty < 1 and equity >= prem * self.contract_mult * 0.4:
                    qty = 1
                if qty < 1:
                    continue
                if want == "call":
                    strike = float(round(spot * (1.0 + abs(self.otm_pct))))
                else:
                    strike = float(round(spot * (1.0 - abs(self.otm_pct))))
                expiry = (ts + pd.Timedelta(days=self.dte_days)).strftime("%Y-%m-%d")
                out.append(
                    {
                        "date": date_str,
                        "action": "open",
                        "underlying": code,
                        "legs": [
                            {
                                "type": want,
                                "strike": strike,
                                "expiry": expiry,
                                "qty": qty,
                            }
                        ],
                        "vpa_tag": tag,
                    }
                )
                open_pos[code] = {
                    "type": want,
                    "strike": strike,
                    "expiry": expiry,
                    "qty": qty,
                    "entry_spot": spot,
                    "entry_ts": ts,
                    "mtm": 0.0,
                }
                equity -= qty * prem * self.contract_mult
                equity = max(equity, self.initial_cash * 0.01)

        return out
