"""Closed long-episode metrics reconstructed from causal execution fills."""
from __future__ import annotations

import math
from typing import Any

import pandas as pd


def wilson_interval(wins: int, total: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if total <= 0:
        return None, None
    rate = float(wins) / float(total)
    denominator = 1.0 + z * z / total
    center = (rate + z * z / (2.0 * total)) / denominator
    half_width = z * math.sqrt(
        rate * (1.0 - rate) / total + z * z / (4.0 * total * total)
    ) / denominator
    return max(0.0, center - half_width), min(1.0, center + half_width)


def long_episode_metrics(
    trades: pd.DataFrame,
    *,
    initial_cash: float | None = None,
    final_value: float | None = None,
    quantity_tolerance: float = 1e-6,
) -> dict[str, Any]:
    """Collapse entry/resize/exit fills into economically closed episodes.

    ``pnl`` is assumed to be the realized gross P&L on sell fills; commissions
    from every buy and sell are deducted. This matches the causal execution
    ledger and avoids counting partial resizes as independent wins or losses.
    """
    required = {"timestamp", "code", "side", "price", "qty", "pnl"}
    missing = sorted(required.difference(trades.columns))
    if missing:
        raise ValueError(f"trade ledger missing columns: {missing}")
    data = trades.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"])
    data = data.sort_values(["code", "timestamp"], kind="stable")
    episodes: list[dict[str, Any]] = []
    open_episodes = 0

    for code, group in data.groupby("code", sort=True):
        quantity = 0.0
        net_pnl = 0.0
        opened_at: pd.Timestamp | None = None
        entry_notional = 0.0
        for row in group.itertuples(index=False):
            side = str(getattr(row, "side")).strip().lower()
            qty = float(getattr(row, "qty"))
            price = float(getattr(row, "price"))
            pnl = float(getattr(row, "pnl"))
            commission_raw = getattr(row, "commission", 0.0)
            commission = float(commission_raw) if pd.notna(commission_raw) else 0.0
            if not all(math.isfinite(value) for value in (qty, price, pnl, commission)):
                raise ValueError("trade ledger contains non-finite values")
            if qty <= 0.0 or price <= 0.0 or commission < 0.0:
                raise ValueError("trade quantity/price/commission is invalid")

            if side == "buy":
                if quantity <= quantity_tolerance:
                    quantity = 0.0
                    net_pnl = 0.0
                    entry_notional = 0.0
                    opened_at = pd.Timestamp(getattr(row, "timestamp"))
                quantity += qty
                entry_notional += qty * price
                net_pnl -= commission
            elif side == "sell":
                if quantity <= quantity_tolerance or qty > quantity + quantity_tolerance:
                    raise ValueError(f"sell fill exceeds open long quantity for {code}")
                quantity -= qty
                net_pnl += pnl - commission
                if quantity <= quantity_tolerance:
                    episodes.append(
                        {
                            "code": str(code),
                            "opened_at": opened_at,
                            "closed_at": pd.Timestamp(getattr(row, "timestamp")),
                            "net_pnl": net_pnl,
                            "return_on_gross_buys": (
                                net_pnl / entry_notional if entry_notional > 0.0 else None
                            ),
                            "won": net_pnl > 0.0,
                        }
                    )
                    quantity = 0.0
                    net_pnl = 0.0
                    entry_notional = 0.0
                    opened_at = None
            else:
                raise ValueError(f"unsupported trade side: {side}")
        if quantity > quantity_tolerance:
            open_episodes += 1

    count = len(episodes)
    wins = sum(1 for episode in episodes if episode["won"])
    win_rate = float(wins) / count if count else None
    low, high = wilson_interval(wins, count)
    total_net_pnl = float(sum(float(episode["net_pnl"]) for episode in episodes))
    expected_pnl = (
        float(final_value) - float(initial_cash)
        if initial_cash is not None and final_value is not None
        else None
    )
    reconciled = (
        math.isclose(total_net_pnl, expected_pnl, rel_tol=1e-9, abs_tol=1e-6)
        if expected_pnl is not None and open_episodes == 0
        else None
    )
    return {
        "closed_episodes": count,
        "wins": wins,
        "losses": count - wins,
        "win_rate": win_rate,
        "wilson_95_low": low,
        "wilson_95_high": high,
        "open_episodes": open_episodes,
        "closed_episode_net_pnl": total_net_pnl,
        "expected_total_pnl": expected_pnl,
        "reconciles_final_value": reconciled,
    }
