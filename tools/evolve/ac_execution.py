"""Global equity engine with Almgren-Chriss market impact.

Extends the standard GlobalEquityEngine so slippage scales with order size,
expected daily volume, and per-bar volatility. Useful for honest capacity /
impact estimates when trade size becomes a meaningful fraction of ADV.
"""
from __future__ import annotations

import pandas as pd

from backtest.engines.global_equity import GlobalEquityEngine

import impact_model


BARS_PER_DAY = {
    "1m": 390,
    "5m": 78,
    "15m": 26,
    "30m": 13,
    "1H": 7,
    "1D": 1,
}


class AlmgrenChrissGlobalEquityEngine(GlobalEquityEngine):
    """US/HK equity engine with size-dependent AC impact.

    Config keys (in addition to base engine keys):
      - impact_model: must be "almgren_chriss" to select this engine
      - ac_eta: temporary impact coefficient (default 0.1)
      - ac_gamma: permanent impact coefficient (default 0.0)
      - ac_beta: participation-rate exponent (default 0.5, square-root law)
      - ac_adv_days: ADV lookback in trading days (default 20)
      - ac_vol_days: volatility lookback in trading days (default 20)
    """

    def __init__(self, config: dict, market: str = "us") -> None:
        super().__init__(config, market=market)
        self.eta = float(config.get("ac_eta", 0.1))
        self.gamma = float(config.get("ac_gamma", 0.0))
        self.beta = float(config.get("ac_beta", 0.5))
        self.adv_days = int(config.get("ac_adv_days", 20))
        self.vol_days = int(config.get("ac_vol_days", 20))
        self._bars_per_day = float(
            BARS_PER_DAY.get(str(config.get("interval", "1D")).lower(), 1.0)
        )

    def _execute_bars(self, dates, data_map, close_df, target_pos, codes) -> None:
        """Store date and data map so apply_slippage can access volume history."""
        self._dates = dates
        self._data_map = data_map
        self._last_target_weight = 0.0
        self._last_equity = 0.0
        super()._execute_bars(dates, data_map, close_df, target_pos, codes)

    def _rebalance(self, symbol, target_weight, df, ts, equity) -> None:
        """Capture target weight and equity for apply_slippage."""
        self._active_symbol = symbol
        self._last_target_weight = target_weight
        self._last_equity = equity
        super()._rebalance(symbol, target_weight, df, ts, equity)

    def apply_slippage(self, price: float, direction: int) -> float:
        """Base fixed spread + AC temporary/permanent impact per share."""
        base = super().apply_slippage(price, direction)
        if not self._active_symbol or not getattr(self, "_data_map", None):
            return base

        if self._active_symbol not in self._data_map:
            return base

        df = self._data_map[self._active_symbol]
        if not hasattr(self, "_bar_idx") or not hasattr(self, "_dates"):
            return base

        ts = self._dates[self._bar_idx]
        if ts not in df.index:
            return base

        history = df.loc[:ts]
        if len(history) < 2:
            return base

        current_pos = self.positions.get(self._active_symbol)
        if current_pos is not None and direction == -current_pos.direction:
            # closing or reducing
            shares = current_pos.size
        elif abs(self._last_target_weight) > 1e-9:
            # opening
            target_notional = abs(self._last_target_weight) * self._last_equity * self.default_leverage
            shares = target_notional / max(price, 1e-12)
        else:
            return base

        adv = impact_model.estimate_adv(history, self._bars_per_day, self.adv_days)
        vol = impact_model.estimate_volatility(history, self._bars_per_day, self.vol_days)
        impact = impact_model.impact_per_share(
            shares=shares,
            price=price,
            adv=adv,
            volatility=vol,
            eta=self.eta,
            gamma=self.gamma,
            beta=self.beta,
        )
        return base + direction * impact
