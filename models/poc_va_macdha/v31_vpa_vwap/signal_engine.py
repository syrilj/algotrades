"""v31_vpa_vwap — Coulling VPA + soft swing VWAP peg, any stock.

See RESEARCH.md. SIDE=VPA; PEG=soft VWAP; SIZE=vol_z/peg mults.
Loop 2: optional per-symbol VWAP DNA (hard/soft/off) from vwap_dna.json.

Note: backtest AST gate forbids top-level Assign — keep paths inside functions.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import numpy as np
import pandas as pd


def _load_local(mod_name: str, filename: str):
    here = Path(__file__).resolve().parent
    candidates = [
        here / filename,
        Path("/Users/syriljacob/Desktop/TradingAlgoWork/models/poc_va_macdha/v31_vpa_vwap") / filename,
        Path("/Users/syriljacob/Desktop/TradingAlgoWork/models/poc_va_macdha/v30_flip_any") / filename,
    ]
    for p in here.parents:
        candidates.append(p / "models" / "poc_va_macdha" / "v31_vpa_vwap" / filename)
        candidates.append(p / "models" / "poc_va_macdha" / "v30_flip_any" / filename)
    for p in candidates:
        if p.exists():
            spec = importlib.util.spec_from_file_location(mod_name, p)
            mod = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(mod)
            return mod
    raise FileNotFoundError(filename)


def _load_vwap_dna() -> Dict[str, Any]:
    """Load symbol-aware VWAP policy DNA (hard/soft/off per name)."""
    here = Path(__file__).resolve().parent
    candidates = [
        here / "vwap_dna.json",
        Path("/Users/syriljacob/Desktop/TradingAlgoWork/models/poc_va_macdha/v31_vpa_vwap") / "vwap_dna.json",
    ]
    for p in here.parents:
        candidates.append(p / "models" / "poc_va_macdha" / "v31_vpa_vwap" / "vwap_dna.json")
    for p in candidates:
        if p.exists():
            try:
                return json.loads(p.read_text())
            except Exception:  # noqa: BLE001
                continue
    return {
        "defaults": {"policy": "soft", "peg_size_mult": 0.5, "chase_atr": 2.0},
        "by_symbol": {},
    }


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


def _norm(c: str) -> str:
    return str(c).strip().upper()


def _vol_z(vol: pd.Series, n: int = 20) -> pd.Series:
    m = vol.rolling(n, min_periods=max(5, n // 2)).mean()
    s = vol.rolling(n, min_periods=max(5, n // 2)).std(ddof=0)
    return ((vol - m) / s.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(0.0)


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
        self.initial_cash = float(cfg.get("initial_cash", 1_000_000.0))
        self.risk_pct = float(cfg.get("risk_pct", 0.50))
        self.dte_days = int(cfg.get("dte_days", 7))
        self.otm_pct = float(cfg.get("otm_pct", 0.0))
        self.max_hold_days = int(cfg.get("max_hold_days", 5))
        self.quick_target_pct = float(cfg.get("quick_target_pct", 0.03))
        self.cut_pct = float(cfg.get("cut_pct", 0.05))
        self.contract_mult = int(cfg.get("contract_multiplier", 100))
        self.max_contracts = int(cfg.get("max_contracts", 500))
        self.max_open_positions = int(cfg.get("max_open_positions", 3))
        self.vpa_mode = str(cfg.get("vpa_mode", "standard")).lower()
        self.require_peg = bool(cfg.get("require_peg", False))
        self.peg_size_mult = float(cfg.get("peg_size_mult", 0.5))
        self.vol_z_boost = float(cfg.get("vol_z_boost", 1.15))
        self.vol_z_thresh = float(cfg.get("vol_z_thresh", 1.0))
        # Loop 2: per-symbol hard/soft/off from vwap_dna.json
        self.use_symbol_dna = bool(cfg.get("use_symbol_dna", False))
        self.dna = _load_vwap_dna() if self.use_symbol_dna else {}
        raw = cfg.get("codes") or []
        self.allow_codes: Optional[Set[str]] = {_norm(x) for x in raw} if raw else None
        self._vpa = _load_local("v31_vpa", "vpa.py")
        self._vwap = _load_local("v31_vwap", "vwap_peg.py")

    def _allowed(self, code: str) -> bool:
        if self.allow_codes is None:
            return True
        c = _norm(code)
        base = c.replace(".US", "")
        return c in self.allow_codes or base in self.allow_codes or f"{base}.US" in self.allow_codes

    def _symbol_policy(self, code: str) -> Dict[str, Any]:
        """Resolve hard|soft|off + peg_size_mult for one name."""
        defaults = {
            "policy": "soft",
            "peg_size_mult": self.peg_size_mult,
            "chase_atr": 2.0,
        }
        if not self.use_symbol_dna:
            # Global hunt_config: require_peg ⇒ hard; else soft with global mult
            defaults["policy"] = "hard" if self.require_peg else "soft"
            defaults["peg_size_mult"] = self.peg_size_mult
            return defaults
        base = dict(self.dna.get("defaults") or {})
        for k, v in defaults.items():
            base.setdefault(k, v)
        by = self.dna.get("by_symbol") or {}
        key = _norm(code).replace(".US", "")
        if key in by:
            base.update(by[key])
        return base

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        feats: Dict[str, pd.DataFrame] = {}
        for code, df in data_map.items():
            if not self._allowed(code):
                continue
            daily = _to_daily(df)
            if len(daily) < 40:
                continue
            pol = self._symbol_policy(code)
            policy = str(pol.get("policy", "soft")).lower()
            peg_mult = float(pol.get("peg_size_mult", self.peg_size_mult))

            vpa = self._vpa.vpa_frame(daily, look=5, vol_sma=20)
            peg = self._vwap.swing_anchored_vwap(daily)
            vz = _vol_z(daily["volume"])
            f = vpa.join(
                peg[
                    [
                        "vwap",
                        "uptrend",
                        "above_vwap",
                        "below_vwap",
                        "dist_vwap_atr",
                        "chase_long",
                        "chase_short",
                        "call_peg_ok",
                        "put_peg_ok",
                    ]
                ],
                how="left",
            )
            f["vol_z"] = vz.reindex(f.index).fillna(0.0)
            f["vwap_policy"] = policy
            if self.vpa_mode == "sniper" and "call_sniper" in f.columns:
                raw_call, raw_put = f["call_sniper"], f["put_sniper"]
            else:
                raw_call, raw_put = f["call"], f["put"]

            # Soft peg: never hard-kill unless require_peg/hard DNA; always block chase
            f["call_final"] = raw_call.fillna(False) & ~f["chase_long"].fillna(False)
            f["put_final"] = raw_put.fillna(False) & ~f["chase_short"].fillna(False)
            require_here = self.require_peg or policy == "hard"
            if require_here:
                f["call_final"] = f["call_final"] & f["call_peg_ok"].fillna(False)
                f["put_final"] = f["put_final"] & f["put_peg_ok"].fillna(False)
            both = f["call_final"] & f["put_final"]
            f["call_final"] = f["call_final"] & ~both
            f["put_final"] = f["put_final"] & ~both

            # Size: off = ignore peg mult; soft/hard = half size when fighting peg
            if policy == "off":
                sm_c = np.ones(len(f), dtype=float)
                sm_p = np.ones(len(f), dtype=float)
            else:
                sm_c = np.where(f["call_peg_ok"].fillna(False), 1.0, peg_mult)
                sm_p = np.where(f["put_peg_ok"].fillna(False), 1.0, peg_mult)
            f["size_mult_call"] = sm_c.astype(float)
            f["size_mult_put"] = sm_p.astype(float)
            hi = f["vol_z"] >= self.vol_z_thresh
            f.loc[hi, "size_mult_call"] = f.loc[hi, "size_mult_call"] * self.vol_z_boost
            f.loc[hi, "size_mult_put"] = f.loc[hi, "size_mult_put"] * self.vol_z_boost
            nd = f["no_demand"].fillna(False)
            f.loc[nd, "size_mult_call"] = f.loc[nd, "size_mult_call"] * 0.5
            feats[code] = f

        if not feats:
            return []

        idx = sorted(set().union(*[set(x.index) for x in feats.values()]))
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
                move = (spot - entry) / entry if entry else 0.0
                if side == "put":
                    move = -move
                dir_ = 1.0 if side == "call" else -1.0
                pos["mtm"] = pos["qty"] * self.contract_mult * 0.55 * dir_ * (spot - entry)

                exit_now = held >= self.max_hold_days
                if held >= 1 and (move >= self.quick_target_pct or move <= -self.cut_pct):
                    exit_now = True
                if side == "call" and held >= 1 and bool(row.get("red")):
                    exit_now = True
                if side == "put" and held >= 1 and bool(row.get("green")):
                    exit_now = True
                if side == "call" and held >= 1 and bool(row.get("put_final")):
                    exit_now = True
                if side == "put" and held >= 1 and bool(row.get("call_final")):
                    exit_now = True

                if exit_now:
                    tag = self._vpa.tag_bar(row.to_dict())
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
                            "vpa_tag": tag,
                        }
                    )
                    equity = max(equity + float(pos.get("mtm", 0.0)), self.initial_cash * 0.01)
                    del open_pos[code]

            if len(open_pos) >= self.max_open_positions:
                continue

            cands = []
            for code, f in feats.items():
                if ts not in f.index or code in open_pos:
                    continue
                row = f.loc[ts]
                spot = float(row["close"])
                if not np.isfinite(spot) or spot <= 0:
                    continue
                want = None
                sm = 1.0
                if bool(row.get("call_final")):
                    want, sm = "call", float(row.get("size_mult_call", 1.0))
                elif bool(row.get("put_final")):
                    want, sm = "put", float(row.get("size_mult_put", 1.0))
                if want is None:
                    continue
                strength = float(row.get("strength", 0.0) or 0.0) * sm
                iv = float(row.get("iv", 0.55) or 0.55)
                tag = self._vpa.tag_bar(row.to_dict())
                peg = "above" if bool(row.get("above_vwap")) else "below"
                cands.append((strength, code, want, spot, iv, sm, tag, peg))

            cands.sort(key=lambda x: x[0], reverse=True)
            n_new = min(self.max_open_positions - len(open_pos), len(cands))
            if n_new <= 0:
                continue
            per = self.risk_pct / float(n_new)

            for _s, code, want, spot, iv, sm, tag, peg in cands[:n_new]:
                if len(open_pos) >= self.max_open_positions:
                    break
                prem = _est_prem(spot, dte=float(self.dte_days), iv=iv)
                budget = max(equity * per * max(sm, 0.15), 0.0)
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
                        "vwap_peg": peg,
                        "size_mult": sm,
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
