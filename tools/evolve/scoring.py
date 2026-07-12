"""Utility reward: money + risk-adj − drawdown, haircut by sample size."""
from __future__ import annotations

from typing import Any


def reliability(n: int, claim_min: int = 40) -> float:
    """Scale score by sample adequacy; thin n cannot dominate the board."""
    if n <= 0:
        return 0.0
    return min(1.0, float(n) / float(claim_min))


def utility_score(
    row: dict[str, Any],
    *,
    ret_w: float = 1.0,
    sharpe_w: float = 0.35,
    calmar_w: float = 0.15,
    dd_soft: float = 0.15,
    dd_hard: float = 0.25,
    dd_soft_pen: float = 0.55,
    dd_hard_pen: float = 50.0,
    claim_min: int = 40,
    wr_w: float = 0.05,
) -> float:
    """Portfolio utility used for search ranking (not end-to-end RL).

    U = ret + a·min(sharpe,3) + b·calmar − λ·excess_soft_dd − ∞-ish if hard DD
    then multiply by reliability(n).
    """
    if row.get("error") or int(row.get("n") or 0) == 0:
        return -99.0

    ret = float(row.get("ret") or 0.0)
    sh = float(row.get("sharpe") or 0.0)
    dd = abs(float(row.get("dd") or row.get("max_drawdown") or 0.0))
    n = int(row.get("n") or 0)
    wr = float(row.get("wr") or row.get("win_rate") or 0.0)

    calmar = ret / max(dd, 0.02)
    soft_excess = max(0.0, dd - dd_soft)
    hard = dd >= dd_hard

    raw = (
        ret_w * ret
        + sharpe_w * min(sh, 3.0)
        + calmar_w * min(calmar, 10.0)
        + wr_w * wr
        - dd_soft_pen * soft_excess
    )
    if hard:
        raw -= dd_hard_pen

    # Options synthetic: slight down-weight so they don't outrank equity on fantasy PnL
    track = str(row.get("data_track") or "")
    if track == "options_synthetic":
        raw *= 0.85

    return float(raw * reliability(n, claim_min))


def score_gain(row: dict[str, Any]) -> float:
    if row.get("error") or int(row.get("n") or 0) == 0:
        return -9.0
    return float(row.get("ret") or 0.0) * reliability(int(row.get("n") or 0))


def score_risk_adj(row: dict[str, Any]) -> float:
    if row.get("error") or int(row.get("n") or 0) == 0:
        return -9.0
    ret = float(row.get("ret") or 0.0)
    dd = max(abs(float(row.get("dd") or 0.0)), 0.02)
    sh = float(row.get("sharpe") or 0.0)
    n = int(row.get("n") or 0)
    return (ret / dd + 0.15 * min(sh, 3.0)) * reliability(n)


def enrich_scores(row: dict[str, Any], *, dd_hard: float = 0.25, claim_min: int = 40) -> dict[str, Any]:
    out = dict(row)
    out["utility"] = utility_score(out, dd_hard=dd_hard, claim_min=claim_min)
    out["score_gain"] = score_gain(out)
    out["score_risk_adj"] = score_risk_adj(out)
    out["reliability"] = reliability(int(out.get("n") or 0), claim_min)
    return out
