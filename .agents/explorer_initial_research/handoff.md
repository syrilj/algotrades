# Handoff Report — explorer_initial_research

## 1. Observation
We explored and analyzed the codebase at the following locations:
*   **v72 Model:**
    *   File Path: `models/poc_va_macdha/v72_dual_sleeve/signal_engine.py` (lines 160–191)
    *   Description: Implements hierarchical merging of `v71_live_confidence` and `v39d_confluence`.
    *   Code excerpt:
        ```python
        # sniper only
        weight = weight.where(~sniper_only, sn.clip(upper=cap))
        # core only
        weight = weight.where(~core_only, core_w)
        # both
        weight = weight.where(~both, stacked)
        ```
*   **Almgren-Chriss Impact Engine:**
    *   File Path: `tools/evolve/ac_execution.py` (lines 26–108)
    *   Analytical model location: `tools/impact_model.py` (lines 19–58)
    *   Engine class: `AlmgrenChrissGlobalEquityEngine` which overrides `apply_slippage` to add `direction * impact`.
*   **Macro & Regime Features:**
    *   File Path: `tools/evolve/macro_features.py` (long memory, standardized surprises, rolling betas, VIX regimes).
    *   File Path: `tools/institutional_flow/features.py` (OFI, absorption, schedule deviation, VPIN).
*   **Backtest Runner and Ranker:**
    *   Runner Path: `.venv/lib/python3.13/site-packages/backtest/runner.py` (AST checks in lines 245–277, module load in lines 674–699, market engine creation in lines 782–844).
    *   Ranker Path: `tools/dynamic_model_rank.py` (monkeypatch in lines 62–77).

## 2. Logic Chain
*   The research requested identification of four specific modules and how they interact.
*   By viewing the files sequentially:
    1.  We mapped `v72_dual_sleeve`'s conditional merge logic to the code in `signal_engine.py`.
    2.  We verified how `AlmgrenChrissGlobalEquityEngine` calculates temporary and permanent price impact based on trade size, ADV, and volatility in `tools/evolve/ac_execution.py` and `tools/impact_model.py`.
    3.  We analyzed how `tools/dynamic_model_rank.py` monkeypatches `backtest.runner._create_market_engine` with `_create_market_engine_for_local` to intercept engine creation and return `AlmgrenChrissGlobalEquityEngine` when `"impact_model": "almgren_chriss"` is set.
    4.  We examined the specific features generated in `macro_features.py` and `features.py` to confirm that all operations are point-in-time and causal.

## 3. Caveats
*   We did not perform any performance evaluations of these models ourselves, nor did we run any backtests with high trade sizes.
*   We assume that the historical data files are in place under `data_cache/` for any execution validations.
*   We did not review the details of options engines or how options backtests utilize market impact, as they are routed differently in `runner.py`.

## 4. Conclusion
The repository features a decoupled structure. The Almgren-Chriss impact model is integrated cleanly through a monkeypatch-based intercept in `tools/dynamic_model_rank.py`, and the feature-engineering modules are structured to maintain causal compliance (avoiding lookahead bias).

## 5. Verification Method
*   Run the unit tests for macro and institutional flow features:
    ```bash
    .venv/bin/pytest tests/test_institutional_flow.py tests/test_macro_features.py
    ```
*   Verify that `AlmgrenChrissGlobalEquityEngine` can be imported successfully:
    ```bash
    .venv/bin/python -c "from evolve.ac_execution import AlmgrenChrissGlobalEquityEngine; print(AlmgrenChrissGlobalEquityEngine)"
    ```
