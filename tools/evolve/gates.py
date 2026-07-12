"""PASS_BAR + dual claim levels + multi-lock OOS checks."""
from __future__ import annotations

import json
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
    """Same spirit as tools/findings.check_pass_bar, row-shaped metrics."""
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

    pf = f("profit_factor", default=1.0)
    # many rows lack PF — do not fail solely on missing PF if absent
    has_pf = "profit_factor" in row and row["profit_factor"] is not None
    dd = abs(f("dd", "max_drawdown"))
    sharpe = f("sharpe")
    trades = f("n", "trade_count")
    exp = f("expectancy", "expectancy_after_costs", default=0.0)
    reasons: list[str] = []
    if has_pf and pf < float(gates.get("profit_factor_min", 1.2)):
        reasons.append(f"profit_factor {pf:.3f} < {gates['profit_factor_min']}")
    if dd > float(gates.get("max_drawdown_max_abs", 0.25)):
        reasons.append(f"|max_drawdown| {dd:.3f} > {gates['max_drawdown_max_abs']}")
    if sharpe < float(gates.get("sharpe_min", 0.5)):
        reasons.append(f"sharpe {sharpe:.3f} < {gates['sharpe_min']}")
    if trades < float(gates.get("min_trades", 40)):
        reasons.append(f"trade_count {trades:.0f} < {gates['min_trades']}")
    exp_min = gates.get("expectancy_after_costs_min")
    if exp_min is not None and "expectancy" in row and exp < float(exp_min):
        reasons.append(f"expectancy {exp:.4f} < {exp_min}")
    return {
        "passed": len(reasons) == 0,
        "reasons": reasons,
        "snapshot": {
            "profit_factor": pf if has_pf else None,
            "max_drawdown": -dd,
            "sharpe": sharpe,
            "trade_count": trades,
            "win_rate": f("wr", "win_rate"),
        },
        "gates": gates,
    }


def apply_gates(row: dict[str, Any]) -> dict[str, Any]:
    """Annotate pass_bar + claim_level + promote eligibility."""
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
    out["may_auto_promote"] = bool(
        track.may_auto_promote
        and level is ClaimLevel.CLAIM
        and pb["passed"]
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
    }


def dd_hard_from_bar() -> float:
    gates = load_pass_bar().get("gates") or {}
    return float(gates.get("max_drawdown_max_abs", 0.25))


def claim_min_trades() -> int:
    gates = load_pass_bar().get("gates") or {}
    return int(gates.get("min_trades", 40))
