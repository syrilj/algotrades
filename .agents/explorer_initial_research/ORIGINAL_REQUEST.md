## 2026-07-16T23:31:44Z

Please explore the TradingAlgoWork repository and identify:
1. The exact location and structure of the `v72_dual_sleeve` model (and relevant signal engines/wrappers in `models/poc_va_macdha/`).
2. The implementation of `AlmgrenChrissGlobalEquityEngine` in `tools/evolve/ac_execution.py` and how it is activated or configured in backtests.
3. The macro features or regime classification logic, specifically in `tools/evolve/macro_features.py` and `tools/institutional_flow/features.py`, or other places.
4. The backtest runner `backtest.runner.py` and `tools/dynamic_model_rank.py` (dmr) and how they load models and run backtests under the Almgren-Chriss impact model.

Please write your findings to a detailed report at `/Users/syriljacob/Desktop/TradingAlgoWork/.agents/explorer_initial_research/analysis.md`.
Verify your findings and ensure all paths and command usages are correct.
