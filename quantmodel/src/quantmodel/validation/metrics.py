"""Portfolio performance metrics (net of costs)."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd

from quantmodel.backtest.state import BacktestState


def _equity_series(state: BacktestState) -> pd.Series:
    if not state.daily:
        return pd.Series(dtype=float)
    idx = pd.to_datetime([d.date for d in state.daily])
    return pd.Series([d.equity for d in state.daily], index=idx, name="equity")


def max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return float(dd.min())


def sharpe_ratio(returns: pd.Series, periods_per_year: int = 252) -> float:
    if returns.empty or returns.std() == 0:
        return 0.0
    return float(returns.mean() / returns.std() * np.sqrt(periods_per_year))


def sortino_ratio(returns: pd.Series, periods_per_year: int = 252) -> float:
    downside = returns[returns < 0]
    if returns.empty or downside.std() == 0:
        return 0.0
    return float(returns.mean() / downside.std() * np.sqrt(periods_per_year))


def cagr(equity: pd.Series) -> float:
    if len(equity) < 2:
        return 0.0
    days = max((equity.index[-1] - equity.index[0]).days, 1)
    return float((equity.iloc[-1] / equity.iloc[0]) ** (365.25 / days) - 1)


def compute_metrics(
    state: BacktestState,
    config: Mapping[str, Any],
    benchmark_symbol: str = "SPY",
) -> dict[str, Any]:
    equity = _equity_series(state)
    if equity.empty:
        return {
            "n_days": 0,
            "final_equity": float(config["run"]["initial_equity"]),
            "total_return": 0.0,
            "cagr": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "calmar": 0.0,
            "max_drawdown": 0.0,
            "n_fills": 0,
        }
    rets = equity.pct_change().dropna()
    mdd = max_drawdown(equity)
    ann_vol = float(rets.std() * np.sqrt(252)) if not rets.empty else 0.0
    cagr_v = cagr(equity)
    sharpe = sharpe_ratio(rets)
    sortino = sortino_ratio(rets)
    calmar = float(cagr_v / abs(mdd)) if mdd < 0 else 0.0

    fills = state.fills
    sells = [f for f in fills if f.side.value == "SELL" or str(f.side) == "SELL"]
    # trade stats from matched sells
    pnls = []
    for f in sells:
        # approximate using fill reason; realized already tracked
        pass
    win_rate = 0.0
    profit_factor = 0.0
    # Use daily returns expectancy
    expectancy = float(rets.mean()) if not rets.empty else 0.0

    avg_positions = float(np.mean([d.open_positions for d in state.daily]))
    avg_heat = float(np.mean([d.portfolio_heat for d in state.daily]))
    exposure = float(np.mean([d.gross_exposure / d.equity if d.equity else 0 for d in state.daily]))

    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1)
    cost_drag = float(state.total_commissions + state.total_slippage_cost) / float(
        config["run"]["initial_equity"]
    )

    # monthly table extremes
    monthly = rets.resample("ME").apply(lambda x: (1 + x).prod() - 1) if len(rets) else pd.Series(dtype=float)
    worst_month = float(monthly.min()) if len(monthly) else 0.0
    best_month = float(monthly.max()) if len(monthly) else 0.0
    yearly = rets.resample("YE").apply(lambda x: (1 + x).prod() - 1) if len(rets) else pd.Series(dtype=float)
    worst_year = float(yearly.min()) if len(yearly) else 0.0
    best_year = float(yearly.max()) if len(yearly) else 0.0

    skew = float(rets.skew()) if len(rets) > 2 else 0.0
    kurt = float(rets.kurtosis()) if len(rets) > 3 else 0.0  # excess kurtosis in pandas

    return {
        "n_days": int(len(equity)),
        "final_equity": float(equity.iloc[-1]),
        "total_return": total_return,
        "cagr": cagr_v,
        "annualized_vol": ann_vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "max_drawdown": mdd,
        "avg_positions": avg_positions,
        "avg_portfolio_heat": avg_heat,
        "exposure_pct": exposure,
        "n_fills": len(fills),
        "n_orders": len(state.orders),
        "realized_pnl": float(state.realized_pnl),
        "total_commissions": float(state.total_commissions),
        "total_slippage_cost": float(state.total_slippage_cost),
        "cost_drag": cost_drag,
        "dividends": float(state.total_dividends),
        "kill_switch_events": len(state.kill_switch.events),
        "expectancy_daily": expectancy,
        "worst_month": worst_month,
        "best_month": best_month,
        "worst_year": worst_year,
        "best_year": best_year,
        "return_skew": skew,
        "return_excess_kurtosis": kurt,
        "returns": rets.tolist(),  # for DSR/bootstrap; may be large
    }
