# Original User Request

## Initial Request — 2026-07-16T23:31:10Z

An adaptive live trading model that dynamically adjusts to market regimes (e.g., volatility, trend/chop) to maximize win rate and maintain stable returns under realistic transaction costs.

Working directory: `/Users/syriljacob/Desktop/TradingAlgoWork/runs/adaptive_live_model`
Integrity mode: development

## Requirements

### R1. Adaptive Regime model
The agent team will implement a new model (e.g. `v83_adaptive_regime`) that dynamically identifies market regimes (such as trend vs chop, risk-on vs risk-off, or high vs low volatility) and uses this information to dynamically filter entries, exits, or adjust position sizing. The team can choose the best approach (e.g., routing between sleeves, macro/regime gates, or walk-forward meta-classification).

### R2. Almgren-Chriss Impact Engine Integration
The backtests must utilize the `AlmgrenChrissGlobalEquityEngine` (defined in `tools/evolve/ac_execution.py`) to simulate transaction costs, permanent/temporary impact, and size-dependent slippage.

### R3. Walk-Forward Backtesting and Evaluation
The model must be backtested on a specified set of assets (e.g. the standard `EQUITY_WINNER_BAG` of `["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "XLP.US", "QQQ.US"]` or a larger liquid asset set) with standard backtest settings ($1,000/higher initial cash, 1H interval, local source, period 2024-08-01 to 2026-07-11).

## Acceptance Criteria

### Execution & Verification
- [ ] The model backtest runs successfully with Almgren-Chriss impact model enabled (`ac_eta` and `ac_gamma` configured).
- [ ] A comparative report is generated contrasting the new model's metrics against the `v72_dual_sleeve` baseline.

### Performance Target
- [ ] Win rate (WR) of closed trades is >= 75% across the full backtest period.
- [ ] Maximum drawdown is <= 20% across the full period.
- [ ] Number of closed trades (n) is >= 30.
- [ ] Net return is positive.
