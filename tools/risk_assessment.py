#!/usr/bin/env python3
"""Research-backed risk assessment engine.

Implements the core risk toolkit from the London Strategic Edge risk management
series (position sizing / Kelly, VaR / Expected Shortfall, drawdown, correlation
/ portfolio risk, and risk-adjusted ratios: Sharpe, Sortino, Calmar).

The engine is analytical, not prescriptive. It reports risk metrics; the existing
``tools/risk_manager.py`` remains the source of live trading actions (plan,
check-open, status).  Where possible we reuse its drawdown / portfolio-mode
utilities so thresholds stay aligned.

CLI:
    python3 tools/risk_assessment.py assess --json-file /tmp/in.json --json
    python3 tools/risk_assessment.py assess --account 10000 --equity 9500 --peak 12000 --returns 0.01,-0.02,0.005,0.015,-0.01 --json
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

# Reuse live risk-manager primitives so thresholds (soft/halt/flatten) never drift.
# We fall back to local copies if the import is not on PYTHONPATH.
try:
    from risk_manager import PortfolioState, drawdown, load_policy, portfolio_mode
except Exception:  # noqa: BLE001
    # Local minimal copies for standalone / notebook usage.
    def drawdown(equity: float, peak: float) -> float:
        if peak <= 0:
            return 0.0
        return max(0.0, (peak - equity) / peak)

    @dataclass
    class PortfolioState:  # type: ignore[no-redef]
        equity: float
        peak: float
        open_equity_n: int = 0
        open_options_n: int = 0
        trade_pnl_history: list[float] = field(default_factory=list)

    def _default_policy() -> dict[str, Any]:
        return {
            "drawdown": {"soft_throttle": 0.08, "halt_new": 0.18, "flatten": 0.28},
        }

    def load_policy(path: Any = None) -> dict[str, Any]:  # noqa: ARG001
        return _default_policy()

    def portfolio_mode(state: PortfolioState, pol: dict[str, Any]) -> tuple[str, list[str]]:
        dd = drawdown(state.equity, state.peak)
        d = pol["drawdown"]
        reasons: list[str] = []
        if dd >= float(d["flatten"]):
            reasons.append(f"DD {dd:.1%} >= flatten {float(d['flatten']):.0%}")
            return "FLATTEN", reasons
        if dd >= float(d["halt_new"]):
            reasons.append(f"DD {dd:.1%} >= halt_new {float(d['halt_new']):.0%}")
            return "HALT_NEW", reasons
        if dd >= float(d["soft_throttle"]):
            reasons.append(f"DD {dd:.1%} in soft throttle")
            return "SIZE_DOWN", reasons
        return "RISK_OK", reasons


ROOT = Path(__file__).resolve().parents[1]


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return v if np.isfinite(v) else default


def _parse_comma_floats(s: str | None) -> list[float]:
    if not s:
        return []
    out = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        out.append(_safe_float(part))
    return out


def _as_array(values: list[float] | np.ndarray | None) -> np.ndarray:
    if values is None:
        return np.array([])
    return np.asarray(values, dtype=float)


def _kelly_fraction(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """f* = (p*b - q) / b where b = avg_win / avg_loss.

    Returns 0.0 when no edge or no loss data.
    """
    if avg_loss <= 0 or not (0.0 <= win_rate <= 1.0):
        return 0.0
    b = avg_win / avg_loss
    q = 1.0 - win_rate
    kelly = (win_rate * b - q) / b
    return max(0.0, kelly)


def _kelly_from_closed_pnl(closed_pnl: list[float]) -> dict[str, float]:
    """Derive win rate, avg win/loss from per-trade PnL percentages."""
    arr = _as_array(closed_pnl)
    if len(arr) == 0:
        return {"win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0, "kelly": 0.0}
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    n = len(arr)
    win_rate = float(len(wins) / n) if n > 0 else 0.0
    avg_win = float(np.mean(wins)) if len(wins) > 0 else 0.0
    avg_loss = float(abs(np.mean(losses))) if len(losses) > 0 else 0.0
    kelly = _kelly_fraction(win_rate, avg_win, avg_loss)
    return {"win_rate": win_rate, "avg_win": avg_win, "avg_loss": avg_loss, "kelly": kelly}


def _kelly_sizes(
    account: float,
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    kelly_mult: float = 0.5,
) -> dict[str, float]:
    kelly = _kelly_fraction(win_rate, avg_win, avg_loss)
    full = kelly * account
    half = kelly * 0.5 * account
    quarter = kelly * 0.25 * account
    # The recommended practice size is half-Kelly unless the caller overrides.
    recommended = kelly * kelly_mult * account
    return {
        "full": kelly,
        "half": kelly * 0.5,
        "quarter": kelly * 0.25,
        "recommended_fraction": kelly * kelly_mult,
        "full_dollar": full,
        "half_dollar": half,
        "quarter_dollar": quarter,
        "recommended_dollar": recommended,
    }


def _fixed_fractional_position(account: float, risk_pct: float, stop_loss_dollars: float) -> float:
    """Position size for a fixed-fraction-of-account stop."""
    if stop_loss_dollars <= 0 or risk_pct <= 0 or account <= 0:
        return 0.0
    risk_dollars = account * risk_pct
    return risk_dollars / stop_loss_dollars


def _parametric_var_es(
    returns: np.ndarray,
    portfolio_value: float,
    confidence: float = 0.95,
    holding_period_days: int = 1,
) -> dict[str, float]:
    """Parametric (variance-covariance) VaR / Expected Shortfall.

    VaR = P * sigma * Z * sqrt(T)
    ES  = P * sigma * phi(Z) / (1 - alpha) * sqrt(T)
    """
    from scipy.stats import norm

    if len(returns) < 2 or portfolio_value <= 0 or not (0.0 < confidence < 1.0):
        return {"var": 0.0, "es": 0.0}
    sigma = float(np.std(returns, ddof=1))
    if sigma <= 0 or not np.isfinite(sigma):
        return {"var": 0.0, "es": 0.0}
    z = float(norm.ppf(confidence))
    pdf_z = float(norm.pdf(z))
    scale = float(np.sqrt(holding_period_days))
    var = portfolio_value * sigma * z * scale
    es = portfolio_value * sigma * (pdf_z / (1.0 - confidence)) * scale
    return {"var": max(0.0, var), "es": max(0.0, es)}


def _historical_var_es(
    returns: np.ndarray,
    portfolio_value: float,
    confidence: float = 0.95,
) -> dict[str, float]:
    """Historical simulation VaR / Expected Shortfall."""
    if len(returns) == 0 or portfolio_value <= 0 or not (0.0 < confidence < 1.0):
        return {"var": 0.0, "es": 0.0}
    percentile = float(np.percentile(returns, (1.0 - confidence) * 100.0))
    # VaR is a positive loss number; the percentile is the return (typically negative).
    var = max(0.0, -portfolio_value * percentile)
    tail = returns[returns <= percentile]
    if len(tail) == 0:
        es = var
    else:
        es = max(0.0, -portfolio_value * float(np.mean(tail)))
    return {"var": var, "es": es}


def _drawdown_metrics(equity: float, peak: float, equity_curve: np.ndarray | None = None) -> dict[str, float]:
    """Compute current drawdown, max drawdown, average drawdown, and max duration."""
    current = drawdown(equity, peak)
    if equity_curve is None or len(equity_curve) == 0:
        return {
            "current": current,
            "max": current,
            "average": current,
            "max_duration_days": 0,
        }
    curve = np.asarray(equity_curve, dtype=float)
    if len(curve) == 0:
        return {"current": current, "max": current, "average": current, "max_duration_days": 0}
    running_max = np.maximum.accumulate(curve)
    dd_series = np.where(running_max > 0, (running_max - curve) / running_max, 0.0)
    max_dd = max(current, float(np.max(dd_series)))
    avg_dd = float(np.mean(dd_series))
    # Max duration: longest stretch where the curve stays below the running max.
    max_dur = 0
    current_dur = 0
    for i in range(len(curve)):
        if curve[i] < running_max[i]:
            current_dur += 1
        else:
            current_dur = 0
        if current_dur > max_dur:
            max_dur = current_dur
    return {
        "current": current,
        "max": max_dd,
        "average": avg_dd,
        "max_duration_days": max_dur,
    }


def _risk_adjusted_ratios(
    returns: np.ndarray,
    risk_free_annual: float = 0.04,
    periods_per_year: int = 252,
    max_drawdown: float = 0.0,
) -> dict[str, float]:
    """Sharpe, Sortino, and Calmar ratios."""
    if len(returns) == 0 or periods_per_year <= 0:
        return {"sharpe": 0.0, "sortino": 0.0, "calmar": 0.0}
    mean_p = float(np.mean(returns))
    risk_free_period = risk_free_annual / periods_per_year
    excess = mean_p - risk_free_period
    sigma = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.0
    sharpe = 0.0
    if sigma > 0 and np.isfinite(sigma):
        sharpe = float((excess / sigma) * np.sqrt(periods_per_year))
    downside = returns[returns < risk_free_period]
    downside_std = float(np.std(downside, ddof=1)) if len(downside) > 1 else 0.0
    sortino = 0.0
    if downside_std > 0 and np.isfinite(downside_std):
        sortino = float((excess / downside_std) * np.sqrt(periods_per_year))
    annual_return = mean_p * periods_per_year
    calmar = 0.0
    if max_drawdown > 0 and np.isfinite(max_drawdown):
        calmar = annual_return / max_drawdown
    return {"sharpe": sharpe, "sortino": sortino, "calmar": calmar}


def _position_returns_matrix(positions: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    """Convert position list to a weights vector and aligned returns matrix.

    Returns are aligned to the most recent ``min_len`` observations shared across
    positions.  Weights are normalized to sum to 1 if their sum is positive.
    """
    if not positions:
        return np.array([]), np.empty((0, 0))
    rets = []
    weights = []
    min_len = None
    for p in positions:
        r = _as_array(p.get("returns"))
        if len(r) == 0:
            continue
        rets.append(r)
        weights.append(_safe_float(p.get("weight"), 1.0))
        if min_len is None or len(r) < min_len:
            min_len = len(r)
    if not rets or min_len is None or min_len == 0:
        return np.array(weights), np.empty((0, 0))
    # Align to the most recent min_len bars for each position.
    aligned = np.vstack([r[-min_len:] for r in rets])
    w = np.asarray(weights, dtype=float)
    total = float(np.sum(w))
    if total > 0:
        w = w / total
    return w, aligned


def _portfolio_metrics(positions: list[dict[str, Any]]) -> dict[str, float]:
    """Portfolio variance, std, and diversification benefit."""
    weights, matrix = _position_returns_matrix(positions)
    if len(weights) == 0 or matrix.size == 0:
        return {"variance": 0.0, "std": 0.0, "diversification_benefit_pct": 0.0}
    # Compute covariance with Bessel's correction (sample covariance).
    if matrix.shape[0] == 1:
        cov = np.array([[float(np.var(matrix[0], ddof=1))]])
    else:
        cov = np.cov(matrix, rowvar=True, ddof=1)
    if cov.size == 0 or np.any(~np.isfinite(cov)):
        return {"variance": 0.0, "std": 0.0, "diversification_benefit_pct": 0.0}
    port_var = float(weights.T @ cov @ weights)
    diag = np.diag(cov)
    weighted_avg_var = float(np.sum(weights * diag))
    div_benefit = 0.0
    if weighted_avg_var > 0 and np.isfinite(weighted_avg_var):
        div_benefit = max(0.0, (weighted_avg_var - port_var) / weighted_avg_var) * 100.0
    std = float(np.sqrt(max(0.0, port_var)))
    return {
        "variance": port_var,
        "std": std,
        "diversification_benefit_pct": div_benefit,
    }


def _build_equity_curve(
    equity: float,
    peak: float,
    returns: np.ndarray,
    equity_curve: np.ndarray | None = None,
) -> np.ndarray:
    """Build an equity curve for drawdown calculations.

    Priority:
    1. Use an explicit ``equity_curve`` if provided.
    2. Reconstruct from ``returns`` scaled to start at ``peak`` and end at ``equity``.
    3. Fallback to ``[peak, equity]``.
    """
    if equity_curve is not None and len(equity_curve) > 0:
        return np.asarray(equity_curve, dtype=float)
    if len(returns) == 0:
        return np.array([peak, equity])
    raw = np.cumprod(1.0 + returns)
    cumret = raw - 1.0
    first = float(cumret[0])
    last = float(cumret[-1])
    denom = last - first
    if denom == 0 or not np.isfinite(denom):
        return np.array([peak, equity])
    desired = equity / peak - 1.0
    scale = desired / denom
    scaled = 1.0 + (cumret - first) * scale
    curve = peak * scaled
    if len(curve) > 0 and curve[-1] != 0:
        curve = curve / curve[-1] * equity
    return curve


@dataclass
class RiskAssessment:
    ok: bool
    account: float
    equity: float
    peak: float
    drawdown: float
    mode: str
    mode_reasons: list[str]
    kelly: dict[str, float]
    position_sizing: dict[str, Any]
    var_es: dict[str, Any]
    risk_adjusted: dict[str, float]
    drawdown_metrics: dict[str, float]
    portfolio: dict[str, float]
    reasons: list[str]
    asof_utc: str


def assess(payload: dict[str, Any]) -> RiskAssessment:
    """Run the full risk assessment from a JSON payload."""
    now = datetime.now(timezone.utc).isoformat()
    account = _safe_float(payload.get("account"), 0.0)
    equity = _safe_float(payload.get("equity"), account)
    peak = _safe_float(payload.get("peak"), equity)
    confidence = _safe_float(payload.get("confidence"), 0.95)
    confidence = max(0.001, min(0.999, confidence))
    holding_days = max(1, int(_safe_float(payload.get("holding_days"), 1.0)))
    risk_free = _safe_float(payload.get("risk_free"), 0.04)
    returns = _as_array(payload.get("returns"))
    closed_pnl = _as_array(payload.get("closed_pnl"))
    positions = payload.get("positions") or []
    if not isinstance(positions, list):
        positions = []
    stop_loss = _safe_float(payload.get("stop_loss_dollars"), 0.0)
    risk_pct = _safe_float(payload.get("risk_pct"), 0.01)

    # Use provided peak or make sure it is at least current equity.
    peak = max(peak, equity)

    # Kelly sizing from closed PnL.
    kelly_stats = _kelly_from_closed_pnl(closed_pnl.tolist())
    kelly = _kelly_sizes(
        account,
        kelly_stats["win_rate"],
        kelly_stats["avg_win"],
        kelly_stats["avg_loss"],
        kelly_mult=0.5,
    )
    reasons: list[str] = []
    if kelly["full"] <= 0:
        reasons.append("Kelly <= 0: no edge detected from closed PnL")
    else:
        reasons.append(f"Kelly {kelly['full']:.2%} -> half {kelly['half']:.2%} (recommended)")

    # Fixed fractional position sizing.
    fixed_position = _fixed_fractional_position(account, risk_pct, stop_loss)
    position_sizing = {
        "fixed_fractional": {
            "shares": fixed_position,
            "risk_dollars": account * risk_pct,
            "risk_pct": risk_pct,
            "stop_loss_dollars": stop_loss,
        }
    }

    # VaR / ES.
    portfolio_value = equity if equity > 0 else account
    var_es = {
        "parametric": _parametric_var_es(returns, portfolio_value, confidence, holding_days),
        "historical": _historical_var_es(returns, portfolio_value, confidence),
        "confidence": confidence,
        "holding_days": holding_days,
    }

    # Drawdown and risk-adjusted ratios.
    user_curve = _as_array(payload.get("equity_curve"))
    if len(user_curve) == 0:
        user_curve = None
    equity_curve = _build_equity_curve(equity, peak, returns, user_curve)
    peak = max(peak, float(np.max(equity_curve)))
    dd_metrics = _drawdown_metrics(equity, peak, equity_curve)
    risk_adj = _risk_adjusted_ratios(returns, risk_free, max_drawdown=dd_metrics["max"])

    # Portfolio variance from positions.
    port_metrics = _portfolio_metrics(positions)

    # Portfolio mode / verdict using risk_manager thresholds.
    state = PortfolioState(equity=equity, peak=peak, trade_pnl_history=closed_pnl.tolist())
    policy = load_policy()
    mode, mode_reasons = portfolio_mode(state, policy)
    # Re-label for an assessment-only readout.
    if mode == "EQUITY_HEDGE":
        mode = "SIZE_DOWN" if dd_metrics["current"] >= float(policy["drawdown"]["soft_throttle"]) else "RISK_OK"
    mode_reasons = [f"mode: {mode}"] + mode_reasons

    reasons.extend(mode_reasons)
    if dd_metrics["current"] > 0:
        reasons.append(f"current drawdown {dd_metrics['current']:.1%}")
    reasons.append(f"95% historical VaR ${var_es['historical']['var']:,.0f}")

    return RiskAssessment(
        ok=True,
        account=account,
        equity=equity,
        peak=peak,
        drawdown=dd_metrics["current"],
        mode=mode,
        mode_reasons=mode_reasons,
        kelly=kelly,
        position_sizing=position_sizing,
        var_es=var_es,
        risk_adjusted=risk_adj,
        drawdown_metrics=dd_metrics,
        portfolio=port_metrics,
        reasons=reasons,
        asof_utc=now,
    )


def _load_payload(args: argparse.Namespace) -> dict[str, Any]:
    """Build the assessment payload from CLI flags or a JSON file."""
    if args.json_file:
        path = Path(args.json_file)
        if not path.exists():
            raise FileNotFoundError(f"json file not found: {args.json_file}")
        return json.loads(path.read_text())

    payload: dict[str, Any] = {}
    if args.account is not None:
        payload["account"] = args.account
    if args.equity is not None:
        payload["equity"] = args.equity
    if args.peak is not None:
        payload["peak"] = args.peak
    if args.returns is not None:
        payload["returns"] = _parse_comma_floats(args.returns)
    if args.closed_pnl is not None:
        payload["closed_pnl"] = _parse_comma_floats(args.closed_pnl)
    if args.confidence is not None:
        payload["confidence"] = args.confidence
    if args.holding_days is not None:
        payload["holding_days"] = args.holding_days
    if args.risk_free is not None:
        payload["risk_free"] = args.risk_free
    if args.stop_loss_dollars is not None:
        payload["stop_loss_dollars"] = args.stop_loss_dollars
    if args.risk_pct is not None:
        payload["risk_pct"] = args.risk_pct
    if args.positions:
        payload["positions"] = json.loads(args.positions)
    return payload


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Research-backed risk assessment engine")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("assess", help="Run risk assessment")
    p.add_argument("--json-file", help="Path to JSON input file")
    p.add_argument("--account", type=float)
    p.add_argument("--equity", type=float)
    p.add_argument("--peak", type=float)
    p.add_argument("--returns", help="Comma-separated daily returns, e.g. 0.01,-0.02,0.005")
    p.add_argument("--closed-pnl", help="Comma-separated per-trade PnL %")
    p.add_argument("--confidence", type=float)
    p.add_argument("--holding-days", type=int)
    p.add_argument("--risk-free", type=float)
    p.add_argument("--stop-loss-dollars", type=float)
    p.add_argument("--risk-pct", type=float)
    p.add_argument("--positions", help="JSON array of {symbol, weight, returns}")
    p.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)
    if args.cmd != "assess":
        ap.print_help()
        return 1

    try:
        payload = _load_payload(args)
        result = assess(payload)
        out = asdict(result)
    except Exception as e:  # noqa: BLE001
        out = {"ok": False, "error": str(e)}

    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
