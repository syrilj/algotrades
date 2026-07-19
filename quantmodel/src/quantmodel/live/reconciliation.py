"""Paper fill reconciliation helpers."""

from __future__ import annotations

from typing import Iterable

from quantmodel.types import Fill


def reconcile_fills(expected: Iterable[Fill], actual: Iterable[Fill], tol_price: float = 0.01) -> dict:
    exp = list(expected)
    act = list(actual)
    mismatches = []
    if len(exp) != len(act):
        mismatches.append(f"count expected={len(exp)} actual={len(act)}")
    for e, a in zip(exp, act):
        if e.shares != a.shares:
            mismatches.append(f"{e.fill_id}: shares {e.shares} vs {a.shares}")
        if abs(e.fill_price - a.fill_price) > tol_price:
            mismatches.append(f"{e.fill_id}: price {e.fill_price} vs {a.fill_price}")
    return {"ok": len(mismatches) == 0, "mismatches": mismatches}
