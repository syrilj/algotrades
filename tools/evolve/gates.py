"""PASS_BAR + dual claim levels + multi-lock OOS checks."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from evolve.data_contracts import (  # noqa: E402
    ClaimLevel,
    DataTrack,
    annotate_row,
    claim_level_from_n,
    infer_track,
)

PASS_BAR_PATH = ROOT / "models" / "_shared" / "PASS_BAR.json"


def load_pass_bar() -> dict[str, Any]:
    if not PASS_BAR_PATH.exists():
        return {
            "gates": {
                "profit_factor_min": 1.2,
                "max_drawdown_max_abs": 0.25,
                "sharpe_min": 0.5,
                "min_trades": 40,
            }
        }
    return json.loads(PASS_BAR_PATH.read_text())


def check_pass_bar(row: dict[str, Any]) -> dict[str, Any]:
    """Evaluate configured promotion metrics, failing closed on missing inputs.

    PASS_BAR is a promotion contract.  A configured metric that was not
    computed is therefore a failed gate, not an implicit neutral/default value.
    Legacy metric names (``pf``, ``n`` and ``expectancy``) remain supported.
    """
    bar = load_pass_bar()
    gates = bar.get("gates") or {}
    if row.get("error"):
        return {"passed": False, "reasons": [f"error:{row['error']}"], "gates": gates}

    def f(key: str, *alts: str, default: float = 0.0) -> float:
        for k in (key, *alts):
            if k in row and row[k] is not None:
                try:
                    v = float(row[k])
                    return default if v != v else v
                except (TypeError, ValueError):
                    pass
        return default

    def present(*keys: str) -> bool:
        for key in keys:
            if key not in row or row[key] is None:
                continue
            try:
                if math.isfinite(float(row[key])):
                    return True
            except (TypeError, ValueError):
                continue
        return False

    pf = f("profit_factor", "pf")
    has_pf = present("profit_factor", "pf")
    dd = abs(f("dd", "max_drawdown"))
    has_dd = present("dd", "max_drawdown")
    sharpe = f("sharpe")
    has_sharpe = present("sharpe")
    trades = f("n", "trade_count")
    has_trades = present("n", "trade_count")
    exp = f("expectancy_after_costs", "expectancy", default=0.0)
    has_exp = present("expectancy_after_costs", "expectancy")
    reasons: list[str] = []
    if "profit_factor_min" in gates:
        if not has_pf:
            reasons.append("missing required metric: profit_factor")
        elif pf < float(gates["profit_factor_min"]):
            reasons.append(f"profit_factor {pf:.3f} < {gates['profit_factor_min']}")
    if "max_drawdown_max_abs" in gates:
        if not has_dd:
            reasons.append("missing required metric: max_drawdown")
        elif dd > float(gates["max_drawdown_max_abs"]):
            reasons.append(f"|max_drawdown| {dd:.3f} > {gates['max_drawdown_max_abs']}")
    if "sharpe_min" in gates:
        if not has_sharpe:
            reasons.append("missing required metric: sharpe")
        elif sharpe < float(gates["sharpe_min"]):
            reasons.append(f"sharpe {sharpe:.3f} < {gates['sharpe_min']}")
    if "min_trades" in gates:
        if not has_trades:
            reasons.append("missing required metric: trade_count")
        elif trades < float(gates["min_trades"]):
            reasons.append(f"trade_count {trades:.0f} < {gates['min_trades']}")
    exp_min = gates.get("expectancy_after_costs_min")
    if exp_min is not None:
        if not has_exp:
            reasons.append("missing required metric: expectancy_after_costs")
        elif exp < float(exp_min):
            reasons.append(f"expectancy_after_costs {exp:.4f} < {exp_min}")
    return {
        "passed": len(reasons) == 0,
        "reasons": reasons,
        "snapshot": {
            "profit_factor": pf if has_pf else None,
            "expectancy_after_costs": exp if has_exp else None,
            "max_drawdown": -dd,
            "sharpe": sharpe,
            "trade_count": trades,
            "win_rate": f("wr", "win_rate"),
        },
        "gates": gates,
    }


def _promotion_evidence_ok(row: dict[str, Any]) -> tuple[bool, list[str]]:
    """Require an untouched final lockbox plus independent multi-lock evidence."""
    evidence = row.get("promotion_evidence")
    if not isinstance(evidence, dict):
        return False, ["missing promotion_evidence"]

    lockbox = evidence.get("lockbox")
    multi_lock = evidence.get("multi_lock")
    reasons: list[str] = []
    if not isinstance(lockbox, dict):
        reasons.append("missing untouched lockbox evidence")
    else:
        if lockbox.get("evaluation_role") not in {"untouched_lockbox", "final_lockbox"}:
            reasons.append("lockbox is not marked untouched")
        if lockbox.get("ok") is not True:
            reasons.append("lockbox did not pass")
        if not lockbox.get("window_id"):
            reasons.append("lockbox window_id missing")
        if lockbox.get("selection_use_forbidden") is not True:
            reasons.append("lockbox is not protected from selection use")
        if not lockbox.get("window_start") or not lockbox.get("window_end"):
            reasons.append("lockbox boundaries missing")
        candidate_id = row.get("id") or row.get("model")
        if candidate_id and lockbox.get("candidate_id") != candidate_id:
            reasons.append("lockbox candidate identity mismatch")

    if not isinstance(multi_lock, dict):
        reasons.append("missing multi-lock evidence")
    else:
        if multi_lock.get("ok") is not True or multi_lock.get("status") != "PASS":
            reasons.append("multi-lock did not pass")
        if int(multi_lock.get("n_holdouts") or 0) < 1:
            reasons.append("multi-lock has no usable holdouts")
    return not reasons, reasons


def apply_gates(row: dict[str, Any]) -> dict[str, Any]:
    """Annotate pass bar, claim level, and final promotion eligibility.

    Compatibility note: research rows without promotion evidence still receive
    their normal claim level, but can no longer be auto-promoted.
    """
    pb = check_pass_bar(row)
    out = dict(row)
    out["pass_bar"] = pb
    out = annotate_row(out)
    # Refine claim with pass_bar
    track = DataTrack(out["data_track"])
    n = int(out.get("n") or 0)
    level = claim_level_from_n(
        n,
        track=track,
        pass_bar_ok=pb["passed"] if track is DataTrack.EQUITY_OHLCV else False,
        error=out.get("error"),
    )
    # Options: max RESEARCH even if n large
    if track is DataTrack.OPTIONS_SYNTHETIC and level is ClaimLevel.CLAIM:
        level = ClaimLevel.RESEARCH
    out["claim_level"] = level.value
    evidence_ok, evidence_reasons = _promotion_evidence_ok(out)
    out["promotion_evidence_ok"] = evidence_ok
    out["promotion_evidence_reasons"] = evidence_reasons
    out["may_auto_promote"] = bool(
        track.may_auto_promote
        and level is ClaimLevel.CLAIM
        and pb["passed"]
        and evidence_ok
        and not out.get("error")
    )
    return out


def multi_lock_verdict(
    lock_results: list[dict[str, Any]],
    *,
    max_wr_drop_pp: float = 15.0,
) -> dict[str, Any]:
    """Compare train-window vs holdout windows for the same frozen model.

    Each item: {tag, ret, wr, n, sharpe, dd, is_holdout: bool}
    """
    train = [r for r in lock_results if not r.get("is_holdout")]
    hold = [r for r in lock_results if r.get("is_holdout")]
    if not hold:
        return {"status": "SKIP", "reason": "no_holdout_rows", "ok": False}
    thin = [r for r in hold if int(r.get("n") or 0) < 5]
    if len(thin) == len(hold):
        return {"status": "THIN", "reason": "all_holdouts_n<5", "ok": False}

    train_wr = sum(float(r.get("wr") or 0) for r in train) / max(len(train), 1)
    flags: list[str] = []
    ok_hold = [r for r in hold if int(r.get("n") or 0) >= 5]
    for r in ok_hold:
        wr = float(r.get("wr") or 0)
        ret = float(r.get("ret") or 0)
        if train and (train_wr - wr) * 100 > max_wr_drop_pp:
            flags.append(f"{r.get('tag')}:wr_drop")
        if ret <= 0 and train and float(train[0].get("ret") or 0) > 0:
            flags.append(f"{r.get('tag')}:ret_flip")
    status = "PASS" if not flags else "FAIL"
    return {
        "status": status,
        "ok": status == "PASS",
        "flags": flags,
        "train_wr": train_wr,
        "n_holdouts": len(ok_hold),
        "evaluation_role": "multi_lock_validation",
    }


def dd_hard_from_bar() -> float:
    gates = load_pass_bar().get("gates") or {}
    return float(gates.get("max_drawdown_max_abs", 0.25))


def claim_min_trades() -> int:
    gates = load_pass_bar().get("gates") or {}
    return int(gates.get("min_trades", 40))
