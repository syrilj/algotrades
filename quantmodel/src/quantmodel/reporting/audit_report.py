"""Markdown audit report generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


def write_markdown_audit(
    path: Path,
    *,
    metrics: Mapping[str, Any],
    manifest: Mapping[str, Any],
    metadata: Mapping[str, Any],
    promotion: Mapping[str, Any] | None = None,
) -> Path:
    promo = promotion or metrics.get("promotion") or {}
    lines = [
        f"# Audit Report — {manifest.get('run_name', '')}",
        "",
        f"**Run ID:** `{manifest.get('run_id', '')}`  ",
        f"**Experiment #:** {manifest.get('experiment_number', '')}  ",
        f"**Git commit:** `{manifest.get('git_commit', '')}` (dirty={manifest.get('git_dirty_flag')})  ",
        f"**Config hash:** `{manifest.get('config_hash', '')}`  ",
        f"**Data hash:** `{manifest.get('data_manifest_hash', '')}`  ",
        f"**Seed:** {manifest.get('random_seed', '')}  ",
        f"**Deployment status:** **{promo.get('deployment_status', manifest.get('deployment_status', 'UNKNOWN'))}**  ",
        f"**Live routing:** disabled  ",
        "",
        "## Data limitations",
        "",
    ]
    lims = metadata.get("limitations") or []
    if metadata.get("survivorship_bias"):
        lims = list(lims) + ["survivorship_bias"]
    if lims:
        for L in sorted(set(lims)):
            lines.append(f"- {L}")
    else:
        lines.append("- none recorded")
    lines += [
        "",
        "## Performance (net of modeled costs)",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Final equity | {metrics.get('final_equity', 0):,.2f} |",
        f"| Total return | {metrics.get('total_return', 0):.2%} |",
        f"| CAGR | {metrics.get('cagr', 0):.2%} |",
        f"| Sharpe | {metrics.get('sharpe', 0):.3f} |",
        f"| Sortino | {metrics.get('sortino', 0):.3f} |",
        f"| Calmar | {metrics.get('calmar', 0):.3f} |",
        f"| Max drawdown | {metrics.get('max_drawdown', 0):.2%} |",
        f"| Ann. vol | {metrics.get('annualized_vol', 0):.2%} |",
        f"| Fills | {metrics.get('n_fills', 0)} |",
        f"| Cost drag | {metrics.get('cost_drag', 0):.2%} |",
        f"| Avg positions | {metrics.get('avg_positions', 0):.2f} |",
        f"| Avg heat | {metrics.get('avg_portfolio_heat', 0):.2%} |",
        "",
        "## Promotion checks",
        "",
    ]
    for r in promo.get("reasons") or []:
        lines.append(f"- {r}")
    if not promo.get("reasons"):
        lines.append("- (no failing reasons listed)")
    checks = promo.get("checks") or {}
    if checks:
        lines += ["", "```json", str(checks)[:4000], "```", ""]
    lines += [
        "## Principle",
        "",
        "A failed strategy with a complete, reproducible audit trail is more valuable",
        "than a profitable-looking backtest that cannot be trusted.",
        "",
        "This software is research only — not financial advice.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
