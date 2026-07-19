"""Promotion and deployment gate evaluation."""

from __future__ import annotations

from typing import Any, Mapping

from quantmodel.types import DeploymentStatus
from quantmodel.validation.bootstrap import bootstrap_metrics
from quantmodel.validation.deflated_sharpe import deflated_sharpe_probability
from quantmodel.validation.monte_carlo import monte_carlo_drawdowns


def evaluate_promotion(
    metrics: Mapping[str, Any],
    config: Mapping[str, Any],
    metadata: Mapping[str, Any],
    *,
    n_trials: int = 1,
) -> dict[str, Any]:
    promo = config["validation"]["promotion"]
    reasons: list[str] = []
    checks: dict[str, Any] = {}

    sharpe = float(metrics.get("sharpe", 0.0))
    n_days = int(metrics.get("n_days", 0))
    returns = metrics.get("returns") or []
    skew = float(metrics.get("return_skew", 0.0))
    # pandas kurtosis is excess; DSR helper accepts either
    excess_kurt = float(metrics.get("return_excess_kurtosis", 0.0))

    dsr_p = deflated_sharpe_probability(
        observed_sr=sharpe,
        n_obs=max(n_days - 1, 1),
        n_trials=max(n_trials, 1),
        skew=skew,
        kurtosis=excess_kurt,  # treated as excess if small
    )
    checks["deflated_sharpe_probability"] = dsr_p
    checks["sharpe"] = sharpe

    boot = {}
    if returns:
        boot_cfg = config["validation"]["bootstrap"]
        boot = bootstrap_metrics(
            returns,
            samples=int(boot_cfg.get("samples", 500)),
            seed=int(boot_cfg.get("seed", 42)),
        )
        checks["bootstrap"] = boot
        lower = boot.get("sharpe", {}).get("p05", -999)
        checks["bootstrap_sharpe_lower"] = lower
    else:
        lower = -999
        checks["bootstrap_sharpe_lower"] = lower

    mc = {}
    if returns:
        mc = monte_carlo_drawdowns(
            returns,
            samples=min(2000, int(config["validation"]["bootstrap"].get("samples", 500))),
            seed=int(config["run"].get("seed", 42)),
            kill_switch_dd=float(config["risk"]["kill_switch_drawdown"]),
        )
        checks["monte_carlo"] = mc

    # Statistical gates
    stat_pass = True
    if sharpe < float(promo.get("minimum_oos_sharpe", 0.7)):
        stat_pass = False
        reasons.append(f"sharpe {sharpe:.3f} < minimum_oos_sharpe")
    if dsr_p < float(promo.get("minimum_deflated_sharpe_probability", 0.95)):
        stat_pass = False
        reasons.append(f"DSR prob {dsr_p:.3f} < threshold")
    if lower <= float(promo.get("minimum_bootstrap_sharpe_lower_bound", 0.0)):
        stat_pass = False
        reasons.append(f"bootstrap sharpe lower {lower} not > 0")

    # Data gates for deployment
    survivorship = bool(metadata.get("survivorship_bias", config["data"].get("survivorship_bias", True)))
    require_sf = bool(promo.get("require_survivorship_free_data", True))
    data_ok = True
    if require_sf and survivorship:
        data_ok = False
        reasons.append("survivorship_bias present — DEPLOYMENT_BLOCKED")

    limitations = metadata.get("limitations") or []
    if "no_delisted_history" in limitations and require_sf:
        data_ok = False
        if "survivorship_bias present" not in " ".join(reasons):
            reasons.append("no_delisted_history")

    if not data_ok:
        status = DeploymentStatus.DEPLOYMENT_BLOCKED.value
    elif stat_pass:
        status = DeploymentStatus.VALIDATION_PASS.value
    else:
        status = DeploymentStatus.RESEARCH_ONLY.value

    # Never auto-enable live
    if status == DeploymentStatus.VALIDATION_PASS.value and data_ok:
        # still need paper
        status = DeploymentStatus.PAPER_READY.value if data_ok and not survivorship else status

    return {
        "deployment_status": status,
        "statistical_pass": stat_pass,
        "data_pass": data_ok,
        "reasons": reasons,
        "checks": checks,
        "live_routing_enabled": False,
    }
