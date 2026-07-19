"""Health checks for paper/live readiness."""

from __future__ import annotations

from typing import Any, Mapping


def health_report(promotion: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "live_routing_enabled": False,
        "deployment_status": promotion.get("deployment_status"),
        "paper_ready": promotion.get("deployment_status") == "PAPER_READY",
        "notes": "Live order routing is disabled in quantmodel v0.1",
    }
