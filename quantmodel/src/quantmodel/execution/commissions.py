"""Commission model."""

from __future__ import annotations

from typing import Mapping


def commission_for_fill(shares: int, config: Mapping) -> float:
    exe = config["execution"]
    per = float(exe.get("commission_per_share", 0.005))
    minimum = float(exe.get("minimum_commission", 1.0))
    return max(minimum, shares * per)
