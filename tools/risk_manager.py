#!/usr/bin/env python3
"""v25 hybrid risk manager — live + research.

Doctrine (user-locked hybrid):
  - No A+ options setup  → hold / rotate **equities** (participate + hedge time)
  - A+ options setup     → **bet big** within hard risk caps (defined-risk preferred)
  - Losers               → **cut fast** (no hope)
  - Portfolio            → DD throttle → halt → flatten

CLI:
  python3 tools/risk_manager.py plan --account 1000 --conf 0.82 --vol-z 1.5 --qqq-ok
  python3 tools/risk_manager.py check-open --vehicle options --pnl-pct -0.32
  python3 tools/risk_manager.py status --equity 950 --peak 1200 --history -0.1,0.2,0.15
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "models" / "poc_va_macdha" / "v25_regime_grow" / "RISK_POLICY.json"

Mode = Literal["STAND_ASIDE", "EQUITY_HEDGE", "OPTIONS_ATTACK", "FLATTEN", "HALT_NEW"]
Vehicle = Literal["none", "equity", "options"]


def _default_policy() -> dict[str, Any]:
    return {
        "version": "v25_regime_grow",
        "account_floor_pct": 0.50,
        "drawdown": {
            "soft_throttle": 0.08,
            "halt_new": 0.18,
            "flatten": 0.28,
        },
        "equity": {
            "base_risk_pct": 0.01,
            "max_risk_pct": 0.02,
            "max_positions": 4,
            "kelly_fraction": 0.50,
            "min_confidence": 0.60,
            "hedge_when_no_options": True,
        },
        "options": {
            "base_risk_pct": 0.12,
            "attack_risk_pct": 0.22,
            "max_risk_pct": 0.25,
            "max_concurrent": 2,
            "min_confidence": 0.72,
            "attack_confidence": 0.82,
            "prefer_debit_spread": True,
            "min_dte": 14,
            "max_dte": 45,
            "target_delta": 0.40,
            "cut_loser_pct": -0.30,
            "stagnant_sessions": 2,
            "stagnant_opt_move": 0.08,
            "stagnant_und_move": 0.02,
            "trail_arm_pct": 0.40,
            "trail_giveback_pct": 0.25,
            "force_flat_dte": 5,
        },
        "conviction": {
            "weights": {
                "model_conf": 0.40,
                "vol_z": 0.25,
                "trend_ok": 0.20,
                "macro_ok": 0.15,
            },
            "vol_z_full": 2.0,
            "vol_z_half": 1.0,
        },
        "feedback": {
            "streak_full_wins": 3,
            "after_loss_mult": 0.35,
            "after_1_2_wins_mult": 0.70,
            "after_3_wins_mult": 1.15,
            "max_feedback_mult": 1.25,
            "min_feedback_mult": 0.25,
        },
        "macro": {
            "block_xlp_spy_defensive": True,
            "require_qqq_for_attack": True,
        },
    }


def load_policy(path: Path | None = None) -> dict[str, Any]:
    p = path or POLICY_PATH
    base = _default_policy()
    if p.exists():
        try:
            raw = json.loads(p.read_text())
            # shallow merge top-level sections
            for k, v in raw.items():
                if isinstance(v, dict) and isinstance(base.get(k), dict):
                    base[k] = {**base[k], **v}
                else:
                    base[k] = v
        except Exception:  # noqa: BLE001
            pass
    return base


@dataclass
class PortfolioState:
    equity: float
    peak: float
    open_equity_n: int = 0
    open_options_n: int = 0
    trade_pnl_history: list[float] = field(default_factory=list)  # recent closed PnL % or $ sign


@dataclass
class SetupSnapshot:
    symbol: str
    model_conf: float  # 0-1 from engine / desk
    vol_z: float = 0.0
    trend_ok: bool = True
    macro_ok: bool = True  # XLP/SPY not defensive
    qqq_ok: bool = True
    earnings_days: float | None = None  # None = unknown
    iv_crush_risk: bool = False
    options_affordable: bool = True
    liquidity_ok: bool = True
    side: str = "long"  # long only for now


@dataclass
class OpenPosition:
    vehicle: Vehicle
    symbol: str
    entry_premium_or_px: float
    current_premium_or_px: float
    peak_premium_or_px: float
    sessions_held: int = 0
    underlying_move_pct: float = 0.0
    dte_left: int | None = None
    side: str = "long"


@dataclass
class RiskDecision:
    mode: Mode
    vehicle: Vehicle
    action: str  # enter | hold | cut | trail_exit | flatten | skip | size_down
    size_mult: float
    risk_pct: float
    max_loss_dollars: float
    conviction: float
    reasons: list[str]
    exit_rules: dict[str, str]
    policy_version: str
    asof_utc: str


def drawdown(equity: float, peak: float) -> float:
    if peak <= 0:
        return 0.0
    return max(0.0, (peak - equity) / peak)


def feedback_size_mult(history: list[float], pol: dict[str, Any]) -> float:
    """Scale next risk by recent closed-trade outcomes (sign of PnL)."""
    fb = pol["feedback"]
    if not history:
        return 1.0
    last = history[-1]
    if last < 0:
        return float(fb["after_loss_mult"])
    wins = 0
    for p in reversed(history):
        if p > 0:
            wins += 1
        else:
            break
    if wins >= int(fb["streak_full_wins"]):
        m = float(fb["after_3_wins_mult"])
    elif wins >= 1:
        m = float(fb["after_1_2_wins_mult"])
    else:
        m = 1.0
    return float(max(fb["min_feedback_mult"], min(fb["max_feedback_mult"], m)))


def dd_size_mult(dd: float, pol: dict[str, Any]) -> float:
    d = pol["drawdown"]
    if dd >= float(d["flatten"]):
        return 0.0
    if dd >= float(d["halt_new"]):
        return 0.0
    soft = float(d["soft_throttle"])
    if dd <= soft:
        return 1.0
    # linear scale soft → halt
    halt = float(d["halt_new"])
    return float(max(0.0, 1.0 - (dd - soft) / max(halt - soft, 1e-9)))


def conviction_score(setup: SetupSnapshot, pol: dict[str, Any]) -> float:
    w = pol["conviction"]["weights"]
    conf = float(max(0.0, min(1.0, setup.model_conf)))
    vz = float(setup.vol_z)
    full = float(pol["conviction"]["vol_z_full"])
    half = float(pol["conviction"]["vol_z_half"])
    if vz >= full:
        vz_s = 1.0
    elif vz >= half:
        vz_s = 0.5 + 0.5 * (vz - half) / max(full - half, 1e-9)
    elif vz > 0:
        vz_s = 0.25 * (vz / max(half, 1e-9))
    else:
        vz_s = 0.0
    trend = 1.0 if setup.trend_ok else 0.0
    macro = 1.0 if setup.macro_ok else 0.0
    score = (
        float(w["model_conf"]) * conf
        + float(w["vol_z"]) * vz_s
        + float(w["trend_ok"]) * trend
        + float(w["macro_ok"]) * macro
    )
    # penalties
    if setup.earnings_days is not None and setup.earnings_days <= 7:
        score *= 0.65
    if setup.iv_crush_risk:
        score *= 0.70
    if not setup.liquidity_ok:
        score *= 0.40
    return float(max(0.0, min(1.0, score)))


def portfolio_mode(state: PortfolioState, pol: dict[str, Any]) -> tuple[Mode, list[str]]:
    dd = drawdown(state.equity, state.peak)
    d = pol["drawdown"]
    reasons: list[str] = []
    if dd >= float(d["flatten"]):
        reasons.append(f"DD {dd:.1%} ≥ flatten {float(d['flatten']):.0%}")
        return "FLATTEN", reasons
    if dd >= float(d["halt_new"]):
        reasons.append(f"DD {dd:.1%} ≥ halt_new {float(d['halt_new']):.0%}")
        return "HALT_NEW", reasons
    if dd >= float(d["soft_throttle"]):
        reasons.append(f"DD {dd:.1%} in soft throttle")
    return "EQUITY_HEDGE", reasons  # default working mode until setup upgrades


def plan_entry(setup: SetupSnapshot, state: PortfolioState, pol: dict[str, Any] | None = None) -> RiskDecision:
    """Decide vehicle + size for a candidate entry."""
    pol = pol or load_policy()
    now = datetime.now(timezone.utc).isoformat()
    conv = conviction_score(setup, pol)
    dd = drawdown(state.equity, state.peak)
    pmode, preasons = portfolio_mode(state, pol)
    fb = feedback_size_mult(state.trade_pnl_history, pol)
    ddm = dd_size_mult(dd, pol)
    exit_rules = {
        "options_cut": f"exit if premium ≤ {pol['options']['cut_loser_pct']:.0%} from entry",
        "options_stagnant": (
            f"after {pol['options']['stagnant_sessions']} sessions, if |opt| < "
            f"{pol['options']['stagnant_opt_move']:.0%} and und < "
            f"{pol['options']['stagnant_und_move']:.0%} → exit"
        ),
        "options_trail": (
            f"after +{pol['options']['trail_arm_pct']:.0%} premium, exit on "
            f"{pol['options']['trail_giveback_pct']:.0%} giveback from peak"
        ),
        "options_time": f"flat by {pol['options']['force_flat_dte']} DTE",
        "equity_stop": "ATR hard stop + trail after arm (engine); cut if macro flips defensive",
        "portfolio": f"flatten all if DD ≥ {pol['drawdown']['flatten']:.0%}",
    }

    # Hard flatten / halt
    if pmode == "FLATTEN":
        return RiskDecision(
            mode="FLATTEN",
            vehicle="none",
            action="flatten",
            size_mult=0.0,
            risk_pct=0.0,
            max_loss_dollars=0.0,
            conviction=conv,
            reasons=preasons + ["no new risk — flatten open book"],
            exit_rules=exit_rules,
            policy_version=str(pol.get("version", "v25")),
            asof_utc=now,
        )
    if pmode == "HALT_NEW":
        return RiskDecision(
            mode="HALT_NEW",
            vehicle="none",
            action="skip",
            size_mult=0.0,
            risk_pct=0.0,
            max_loss_dollars=0.0,
            conviction=conv,
            reasons=preasons + ["hold existing only; no new entries"],
            exit_rules=exit_rules,
            policy_version=str(pol.get("version", "v25")),
            asof_utc=now,
        )

    if setup.side != "long":
        return RiskDecision(
            mode="STAND_ASIDE",
            vehicle="none",
            action="skip",
            size_mult=0.0,
            risk_pct=0.0,
            max_loss_dollars=0.0,
            conviction=conv,
            reasons=["short side not enabled in v25 hybrid"],
            exit_rules=exit_rules,
            policy_version=str(pol.get("version", "v25")),
            asof_utc=now,
        )

    if not setup.macro_ok and pol["macro"].get("block_xlp_spy_defensive", True):
        return RiskDecision(
            mode="STAND_ASIDE",
            vehicle="none",
            action="skip",
            size_mult=0.0,
            risk_pct=0.0,
            max_loss_dollars=0.0,
            conviction=conv,
            reasons=["macro defensive (XLP/SPY) — stand aside"],
            exit_rules=exit_rules,
            policy_version=str(pol.get("version", "v25")),
            asof_utc=now,
        )

    opt = pol["options"]
    eq = pol["equity"]
    attack_ok = (
        conv >= float(opt["attack_confidence"])
        and setup.model_conf >= float(opt["min_confidence"])
        and setup.options_affordable
        and setup.liquidity_ok
        and (setup.qqq_ok or not pol["macro"].get("require_qqq_for_attack", True))
        and state.open_options_n < int(opt["max_concurrent"])
        and not (setup.earnings_days is not None and setup.earnings_days <= 3)
    )

    if attack_ok:
        # BET BIG within hard cap
        risk_pct = float(opt["attack_risk_pct"]) * fb * max(ddm, 0.35)
        risk_pct = float(min(float(opt["max_risk_pct"]), max(float(opt["base_risk_pct"]), risk_pct)))
        size_mult = float(min(1.25, max(0.5, conv * fb * max(ddm, 0.5))))
        reasons = [
            f"OPTIONS_ATTACK: conviction {conv:.2f} ≥ attack {float(opt['attack_confidence']):.2f}",
            f"feedback×{fb:.2f} dd_mult×{ddm:.2f}",
            "prefer debit spread; defined risk",
            "cut losers fast per exit_rules",
        ]
        if setup.earnings_days is not None and setup.earnings_days <= 7:
            risk_pct = min(risk_pct, float(opt["base_risk_pct"]))
            reasons.append("earnings ≤7d — size capped to base options risk")
        return RiskDecision(
            mode="OPTIONS_ATTACK",
            vehicle="options",
            action="enter",
            size_mult=size_mult,
            risk_pct=risk_pct,
            max_loss_dollars=round(state.equity * risk_pct, 2),
            conviction=conv,
            reasons=reasons + preasons,
            exit_rules=exit_rules,
            policy_version=str(pol.get("version", "v25")),
            asof_utc=now,
        )

    # No A+ options → equity hedge / participate if model has edge
    hedge = bool(eq.get("hedge_when_no_options", True))
    equity_ok = (
        hedge
        and setup.model_conf >= float(eq["min_confidence"])
        and setup.trend_ok
        and state.open_equity_n < int(eq["max_positions"])
        and ddm > 0
    )
    if equity_ok:
        risk_pct = float(eq["base_risk_pct"]) * fb * ddm
        if conv >= 0.75:
            risk_pct = min(float(eq["max_risk_pct"]), risk_pct * 1.25)
        risk_pct = float(min(float(eq["max_risk_pct"]), max(0.005, risk_pct)))
        size_mult = float(min(1.0, max(0.25, setup.model_conf * fb * ddm)))
        why_not_opt = []
        if conv < float(opt["attack_confidence"]):
            why_not_opt.append(f"conviction {conv:.2f} < attack bar")
        if not setup.options_affordable:
            why_not_opt.append("options not affordable / chain skip")
        if not setup.qqq_ok and pol["macro"].get("require_qqq_for_attack", True):
            why_not_opt.append("QQQ trend not ok for attack")
        if state.open_options_n >= int(opt["max_concurrent"]):
            why_not_opt.append("max concurrent options reached")
        return RiskDecision(
            mode="EQUITY_HEDGE",
            vehicle="equity",
            action="enter",
            size_mult=size_mult,
            risk_pct=risk_pct,
            max_loss_dollars=round(state.equity * risk_pct, 2),
            conviction=conv,
            reasons=[
                "EQUITY_HEDGE: park capital in stock edge until A+ options",
                *why_not_opt,
                f"feedback×{fb:.2f} dd_mult×{ddm:.2f}",
            ]
            + preasons,
            exit_rules=exit_rules,
            policy_version=str(pol.get("version", "v25")),
            asof_utc=now,
        )

    return RiskDecision(
        mode="STAND_ASIDE",
        vehicle="none",
        action="skip",
        size_mult=0.0,
        risk_pct=0.0,
        max_loss_dollars=0.0,
        conviction=conv,
        reasons=["no equity edge and no options attack — cash is a position"] + preasons,
        exit_rules=exit_rules,
        policy_version=str(pol.get("version", "v25")),
        asof_utc=now,
    )


def check_open(pos: OpenPosition, pol: dict[str, Any] | None = None) -> RiskDecision:
    """React rules for an open position — cut fast, trail winners."""
    pol = pol or load_policy()
    now = datetime.now(timezone.utc).isoformat()
    opt = pol["options"]
    reasons: list[str] = []
    exit_rules = {
        "cut": f"premium ≤ {opt['cut_loser_pct']:.0%}",
        "trail": f"arm +{opt['trail_arm_pct']:.0%}; giveback {opt['trail_giveback_pct']:.0%} of peak",
        "stagnant": f"{opt['stagnant_sessions']} sessions flat",
        "time": f"≤{opt['force_flat_dte']} DTE",
    }

    if pos.entry_premium_or_px <= 0:
        return RiskDecision(
            mode="STAND_ASIDE",
            vehicle=pos.vehicle,
            action="hold",
            size_mult=1.0,
            risk_pct=0.0,
            max_loss_dollars=0.0,
            conviction=0.0,
            reasons=["invalid entry price"],
            exit_rules=exit_rules,
            policy_version=str(pol.get("version", "v25")),
            asof_utc=now,
        )

    pnl_pct = (pos.current_premium_or_px / pos.entry_premium_or_px) - 1.0
    peak_pct = (pos.peak_premium_or_px / pos.entry_premium_or_px) - 1.0
    giveback_from_peak = 0.0
    if pos.peak_premium_or_px > 0:
        giveback_from_peak = 1.0 - (pos.current_premium_or_px / pos.peak_premium_or_px)

    if pos.vehicle == "options":
        if pnl_pct <= float(opt["cut_loser_pct"]):
            reasons.append(f"CUT: options PnL {pnl_pct:.1%} ≤ {float(opt['cut_loser_pct']):.0%}")
            return RiskDecision(
                mode="OPTIONS_ATTACK",
                vehicle="options",
                action="cut",
                size_mult=0.0,
                risk_pct=0.0,
                max_loss_dollars=0.0,
                conviction=0.0,
                reasons=reasons,
                exit_rules=exit_rules,
                policy_version=str(pol.get("version", "v25")),
                asof_utc=now,
            )
        if pos.dte_left is not None and pos.dte_left <= int(opt["force_flat_dte"]):
            reasons.append(f"TIME: {pos.dte_left} DTE left — force flat")
            return RiskDecision(
                mode="OPTIONS_ATTACK",
                vehicle="options",
                action="cut",
                size_mult=0.0,
                risk_pct=0.0,
                max_loss_dollars=0.0,
                conviction=0.0,
                reasons=reasons,
                exit_rules=exit_rules,
                policy_version=str(pol.get("version", "v25")),
                asof_utc=now,
            )
        if peak_pct >= float(opt["trail_arm_pct"]) and giveback_from_peak >= float(opt["trail_giveback_pct"]):
            reasons.append(
                f"TRAIL: peak {peak_pct:.0%}, giveback {giveback_from_peak:.0%} ≥ "
                f"{float(opt['trail_giveback_pct']):.0%}"
            )
            return RiskDecision(
                mode="OPTIONS_ATTACK",
                vehicle="options",
                action="trail_exit",
                size_mult=0.0,
                risk_pct=0.0,
                max_loss_dollars=0.0,
                conviction=0.0,
                reasons=reasons,
                exit_rules=exit_rules,
                policy_version=str(pol.get("version", "v25")),
                asof_utc=now,
            )
        if (
            pos.sessions_held >= int(opt["stagnant_sessions"])
            and abs(pnl_pct) < float(opt["stagnant_opt_move"])
            and abs(pos.underlying_move_pct) < float(opt["stagnant_und_move"])
        ):
            reasons.append("STAGNANT: no option or underlying move — free capital for next A+")
            return RiskDecision(
                mode="OPTIONS_ATTACK",
                vehicle="options",
                action="cut",
                size_mult=0.0,
                risk_pct=0.0,
                max_loss_dollars=0.0,
                conviction=0.0,
                reasons=reasons,
                exit_rules=exit_rules,
                policy_version=str(pol.get("version", "v25")),
                asof_utc=now,
            )
        return RiskDecision(
            mode="OPTIONS_ATTACK",
            vehicle="options",
            action="hold",
            size_mult=1.0,
            risk_pct=0.0,
            max_loss_dollars=0.0,
            conviction=0.0,
            reasons=[f"hold options; PnL {pnl_pct:+.1%} peak {peak_pct:+.1%}"],
            exit_rules=exit_rules,
            policy_version=str(pol.get("version", "v25")),
            asof_utc=now,
        )

    # equity open: soft rules (hard ATR lives in engine)
    if pnl_pct <= -0.08:
        reasons.append(f"equity soft cut warning: {pnl_pct:.1%} (engine ATR stop is primary)")
    return RiskDecision(
        mode="EQUITY_HEDGE",
        vehicle="equity",
        action="hold",
        size_mult=1.0,
        risk_pct=0.0,
        max_loss_dollars=0.0,
        conviction=0.0,
        reasons=reasons or [f"hold equity; PnL {pnl_pct:+.1%}"],
        exit_rules=exit_rules,
        policy_version=str(pol.get("version", "v25")),
        asof_utc=now,
    )


def decision_to_dict(d: RiskDecision) -> dict[str, Any]:
    return asdict(d)


def _parse_history(s: str) -> list[float]:
    if not s.strip():
        return []
    out = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        out.append(float(part))
    return out


def main(argv: list[str] | None = None) -> int:
    pol = load_policy()
    ap = argparse.ArgumentParser(description="v25 hybrid risk manager")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_plan = sub.add_parser("plan", help="Plan entry vehicle + size")
    p_plan.add_argument("--symbol", default="APLD")
    p_plan.add_argument("--account", type=float, default=1000.0)
    p_plan.add_argument("--peak", type=float, default=0.0, help="Equity high-water (default=account)")
    p_plan.add_argument("--conf", type=float, default=0.70, help="Model confidence 0-1")
    p_plan.add_argument("--vol-z", type=float, default=0.0)
    p_plan.add_argument("--qqq-ok", action="store_true")
    p_plan.add_argument("--no-qqq", action="store_true")
    p_plan.add_argument("--macro-ok", action="store_true", default=True)
    p_plan.add_argument("--defensive", action="store_true", help="XLP/SPY defensive on")
    p_plan.add_argument("--trend-ok", action="store_true", default=True)
    p_plan.add_argument("--no-trend", action="store_true")
    p_plan.add_argument("--earnings-days", type=float, default=-1)
    p_plan.add_argument("--no-options", action="store_true", help="Options chain unaffordable")
    p_plan.add_argument("--open-equity", type=int, default=0)
    p_plan.add_argument("--open-options", type=int, default=0)
    p_plan.add_argument("--history", type=str, default="", help="Recent closed PnL signs, e.g. 1,-1,1")
    p_plan.add_argument("--json", action="store_true")

    p_chk = sub.add_parser("check-open", help="React rules on open position")
    p_chk.add_argument("--vehicle", choices=["options", "equity"], default="options")
    p_chk.add_argument("--symbol", default="APLD")
    p_chk.add_argument("--entry", type=float, required=True)
    p_chk.add_argument("--current", type=float, default=None, help="Current premium/price (or use --pnl-pct)")
    p_chk.add_argument("--peak-px", type=float, default=0.0)
    p_chk.add_argument("--pnl-pct", type=float, default=None, help="Override current via %% from entry")
    p_chk.add_argument("--sessions", type=int, default=0)
    p_chk.add_argument("--und-move", type=float, default=0.0)
    p_chk.add_argument("--dte", type=int, default=None)
    p_chk.add_argument("--json", action="store_true")

    p_st = sub.add_parser("status", help="Portfolio mode from equity/peak")
    p_st.add_argument("--equity", type=float, required=True)
    p_st.add_argument("--peak", type=float, required=True)
    p_st.add_argument("--history", type=str, default="")
    p_st.add_argument("--json", action="store_true")

    p_pol = sub.add_parser("policy", help="Print active RISK_POLICY")
    p_pol.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)

    if args.cmd == "policy":
        print(json.dumps(pol, indent=2))
        return 0

    if args.cmd == "status":
        st = PortfolioState(
            equity=args.equity,
            peak=args.peak,
            trade_pnl_history=_parse_history(args.history),
        )
        mode, reasons = portfolio_mode(st, pol)
        dd = drawdown(st.equity, st.peak)
        out = {
            "mode": mode,
            "drawdown": round(dd, 4),
            "feedback_mult": feedback_size_mult(st.trade_pnl_history, pol),
            "dd_size_mult": dd_size_mult(dd, pol),
            "reasons": reasons,
            "policy": pol.get("version"),
        }
        if args.json:
            print(json.dumps(out, indent=2))
        else:
            print(f"MODE {mode}  DD={dd:.1%}  fb×{out['feedback_mult']:.2f}  dd×{out['dd_size_mult']:.2f}")
            for r in reasons:
                print(" -", r)
        return 0

    if args.cmd == "check-open":
        entry = float(args.entry)
        if args.pnl_pct is not None:
            current = entry * (1.0 + float(args.pnl_pct))
        elif args.current is not None:
            current = float(args.current)
        else:
            print("check-open: pass --current or --pnl-pct", file=sys.stderr)
            return 2
        peak_px = float(args.peak_px) if args.peak_px > 0 else max(entry, current)
        pos = OpenPosition(
            vehicle=args.vehicle,  # type: ignore[arg-type]
            symbol=args.symbol,
            entry_premium_or_px=entry,
            current_premium_or_px=current,
            peak_premium_or_px=peak_px,
            sessions_held=int(args.sessions),
            underlying_move_pct=float(args.und_move),
            dte_left=args.dte,
        )
        dec = check_open(pos, pol)
        d = decision_to_dict(dec)
        if args.json:
            print(json.dumps(d, indent=2))
        else:
            print(f"{dec.action.upper()}  {dec.vehicle}  {args.symbol}")
            for r in dec.reasons:
                print(" -", r)
            print("Exit rules:")
            for k, v in dec.exit_rules.items():
                print(f"  {k}: {v}")
        return 0

    if args.cmd == "plan":
        peak = args.peak if args.peak > 0 else args.account
        setup = SetupSnapshot(
            symbol=args.symbol.upper(),
            model_conf=float(args.conf),
            vol_z=float(args.vol_z),
            trend_ok=not args.no_trend,
            macro_ok=not args.defensive,
            qqq_ok=bool(args.qqq_ok) and not args.no_qqq,
            earnings_days=None if args.earnings_days < 0 else float(args.earnings_days),
            options_affordable=not args.no_options,
            liquidity_ok=True,
        )
        # if user didn't pass --qqq-ok, default True for plan UX unless --no-qqq
        if not args.qqq_ok and not args.no_qqq:
            setup.qqq_ok = True
        state = PortfolioState(
            equity=float(args.account),
            peak=float(peak),
            open_equity_n=int(args.open_equity),
            open_options_n=int(args.open_options),
            trade_pnl_history=_parse_history(args.history),
        )
        dec = plan_entry(setup, state, pol)
        d = decision_to_dict(dec)
        d["symbol"] = setup.symbol
        d["account"] = state.equity
        d["drawdown"] = round(drawdown(state.equity, state.peak), 4)
        if args.json:
            print(json.dumps(d, indent=2))
        else:
            print(f"=== RISK PLAN  {setup.symbol}  account=${state.equity:,.0f} ===")
            print(f"MODE     {dec.mode}")
            print(f"VEHICLE  {dec.vehicle}   ACTION {dec.action}")
            print(f"CONV     {dec.conviction:.2f}   SIZE×{dec.size_mult:.2f}")
            print(f"RISK     {dec.risk_pct:.1%} of book  → max loss ${dec.max_loss_dollars:,.0f}")
            print("WHY")
            for r in dec.reasons:
                print(f"  • {r}")
            print("EXIT (tape this to the ticket)")
            for k, v in dec.exit_rules.items():
                print(f"  {k}: {v}")
            if dec.mode == "OPTIONS_ATTACK":
                print("\nNext:  python3 tools/options_picker.py --symbol", setup.symbol,
                      f"--account {state.equity:.0f} --risk-pct {dec.risk_pct:.2f}")
            elif dec.mode == "EQUITY_HEDGE":
                print("\nNext:  python3 tools/trade_desk.py", setup.symbol,
                      f"--model v25_regime_grow --account {state.equity:.0f} --risk-pct {dec.risk_pct:.4f}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
