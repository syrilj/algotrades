"""Equity-curve kill switch with shadow equity resume."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional


@dataclass
class KillSwitchState:
    active: bool = False
    peak_equity: float = 0.0
    shadow_equity: float = 0.0
    shadow_peak: float = 0.0
    activated_on: Optional[date] = None
    resumed_on: Optional[date] = None
    events: List[dict] = field(default_factory=list)

    def update_live(
        self,
        *,
        asof: date,
        equity: float,
        strategy_equity_if_active: float,
        kill_dd: float,
        resume_dd: float,
    ) -> None:
        """
        equity: actual account equity (cash-only while killed).
        strategy_equity_if_active: hypothetical full-strategy MTM for shadow curve.
        """
        if self.peak_equity <= 0:
            self.peak_equity = equity
        self.peak_equity = max(self.peak_equity, equity)
        dd = equity / self.peak_equity - 1.0 if self.peak_equity > 0 else 0.0

        # Shadow always tracks strategy path
        if self.shadow_peak <= 0:
            self.shadow_peak = strategy_equity_if_active
            self.shadow_equity = strategy_equity_if_active
        self.shadow_equity = strategy_equity_if_active
        self.shadow_peak = max(self.shadow_peak, strategy_equity_if_active)
        shadow_dd = (
            self.shadow_equity / self.shadow_peak - 1.0 if self.shadow_peak > 0 else 0.0
        )

        if not self.active and dd <= kill_dd:
            self.active = True
            self.activated_on = asof
            self.events.append(
                {
                    "date": asof.isoformat(),
                    "event": "activate",
                    "equity": equity,
                    "drawdown": dd,
                    "shadow_equity": self.shadow_equity,
                    "shadow_drawdown": shadow_dd,
                }
            )
        elif self.active and shadow_dd >= resume_dd:
            self.active = False
            self.resumed_on = asof
            # reset peak to current equity to avoid instant re-trigger noise
            self.peak_equity = equity
            self.events.append(
                {
                    "date": asof.isoformat(),
                    "event": "resume",
                    "equity": equity,
                    "drawdown": dd,
                    "shadow_equity": self.shadow_equity,
                    "shadow_drawdown": shadow_dd,
                }
            )

    def drawdown(self, equity: float) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return equity / self.peak_equity - 1.0
