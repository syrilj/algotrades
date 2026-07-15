"""Repository-owned execution adapter for causal local-equity research.

It deliberately reopens a same-direction position when its requested target
changes materially.  That is conservative (it charges a full round trip) but
prevents the base engine from silently ignoring model sizing feedback.
"""
from __future__ import annotations

from dataclasses import replace

import pandas as pd

from backtest.engines.global_equity import GlobalEquityEngine
from backtest.models import Position, TradeRecord


class CausalGlobalEquityEngine(GlobalEquityEngine):
    def __init__(self, config: dict, market: str = "us") -> None:
        super().__init__(config, market=market)
        self.us_commission_rate = float(config.get("causal_commission_rate", config.get("commission", 0.0005)))
        self.rebalance_tolerance = float(config.get("rebalance_tolerance", 0.05))

    def calc_commission(self, size: float, price: float, direction: int, is_open: bool) -> float:
        if self.market == "us":
            return abs(float(size) * float(price)) * self.us_commission_rate
        return super().calc_commission(size, price, direction, is_open)

    def _rebalance(self, symbol, target_weight, df, ts, equity) -> None:
        current = self.positions.get(symbol)
        target_dir = 1 if target_weight > 1e-9 else (-1 if target_weight < -1e-9 else 0)
        if current is not None and target_dir == current.direction and target_dir != 0:
            current_weight = (current.size * current.entry_price) / max(float(equity), 1e-12)
            if abs(abs(float(target_weight)) - current_weight) > self.rebalance_tolerance:
                if df is None or ts not in df.index:
                    return
                bar = df.loc[ts]
                open_price = float(bar.get("open", bar.get("close", 0)))
                entry_fill = self.apply_slippage(open_price, current.direction)
                target_notional = abs(float(target_weight)) * float(equity) * current.leverage
                desired_size = self.round_size(self._calc_raw_size(symbol, target_notional, entry_fill), entry_fill)
                delta = desired_size - current.size
                if delta > 0:
                    margin = self._calc_margin(symbol, delta, entry_fill, current.leverage)
                    commission = self.calc_commission(delta, entry_fill, current.direction, is_open=True)
                    if margin + commission <= self.capital:
                        new_size = current.size + delta
                        average_entry = (current.size * current.entry_price + delta * entry_fill) / new_size
                        self.capital -= margin + commission
                        self.positions[symbol] = replace(
                            current,
                            entry_price=average_entry,
                            size=new_size,
                            entry_commission=current.entry_commission + commission,
                        )
                elif delta < 0:
                    reduction = min(-delta, current.size)
                    exit_fill = self.apply_slippage(open_price, -current.direction)
                    pnl = self._calc_pnl(symbol, current.direction, reduction, current.entry_price, exit_fill)
                    margin = self._calc_margin(symbol, reduction, current.entry_price, current.leverage)
                    exit_commission = self.calc_commission(reduction, exit_fill, current.direction, is_open=False)
                    entry_commission = current.entry_commission * (reduction / current.size)
                    self.capital += margin + pnl - exit_commission
                    self.trades.append(TradeRecord(
                        symbol=symbol,
                        direction=current.direction,
                        entry_price=current.entry_price,
                        exit_price=exit_fill,
                        entry_time=current.entry_time,
                        exit_time=ts,
                        size=reduction,
                        leverage=current.leverage,
                        pnl=pnl,
                        pnl_pct=(pnl / margin * 100 if margin > 1e-12 else 0.0),
                        exit_reason="target_resize",
                        holding_bars=max(self._bar_idx - current.entry_bar_idx, 0),
                        commission=entry_commission + exit_commission,
                    ))
                    remain = current.size - reduction
                    if remain <= 1e-9:
                        self.positions.pop(symbol, None)
                    else:
                        self.positions[symbol] = replace(
                            current, size=remain, entry_commission=current.entry_commission - entry_commission
                        )
                return
        super()._rebalance(symbol, target_weight, df, ts, equity)

    def _execute_bars(self, dates, data_map, close_df, target_pos, codes) -> None:
        super()._execute_bars(dates, data_map, close_df, target_pos, codes)
        # The parent records its final snapshot before forced liquidation.  Make
        # the last reported point include the same terminal costs as final cash.
        if self.equity_snapshots:
            snapshot = self.equity_snapshots[-1]
            self.equity_snapshots[-1] = replace(
                snapshot, capital=self.capital, unrealized=0.0, equity=self.capital, positions=0
            )

    def _write_artifacts(self, run_dir, data_map, dates, equity_series, bench_equity, bench_ret, target_pos, metrics, codes) -> None:
        super()._write_artifacts(run_dir, data_map, dates, equity_series, bench_equity, bench_ret, target_pos, metrics, codes)
        # BaseEngine serialises dates only, which makes intraday fold and fill
        # audits impossible.  Rewrite the compatible trade artifact with exact
        # timestamps and explicit commission.
        rows = []
        for trade in self.trades:
            rows.extend((
                {
                    "timestamp": pd.Timestamp(trade.entry_time).isoformat(), "code": trade.symbol,
                    "side": "buy" if trade.direction == 1 else "sell", "price": trade.entry_price,
                    "qty": trade.size, "reason": "signal", "pnl": 0.0, "holding_days": 0,
                    "return_pct": 0.0, "commission": trade.commission / 2.0,
                },
                {
                    "timestamp": pd.Timestamp(trade.exit_time).isoformat(), "code": trade.symbol,
                    "side": "sell" if trade.direction == 1 else "buy", "price": trade.exit_price,
                    "qty": trade.size, "reason": trade.exit_reason, "pnl": trade.pnl,
                    "holding_days": trade.holding_bars, "return_pct": trade.pnl_pct,
                    "commission": trade.commission / 2.0,
                },
            ))
        pd.DataFrame(rows).to_csv(run_dir / "artifacts" / "trades.csv", index=False)
