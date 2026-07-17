# Detailed Research Analysis Report

This report presents findings from an exploration of the `TradingAlgoWork` repository, detailing the `v72_dual_sleeve` model, the Almgren-Chriss impact model engine (`AlmgrenChrissGlobalEquityEngine`), macro/regime feature engineering, and the execution/backtesting infrastructure.

---

## 1. Structure and Location of the `v72_dual_sleeve` Model

### Exact Location
The model is defined in the directory:
`models/poc_va_macdha/v72_dual_sleeve/`

Key files in this folder include:
*   `signal_engine.py` (198 lines, 7,738 bytes): Main logic implementing the hierarchical dual-sleeve portfolio.
*   `config.json` (13 lines, 417 bytes): Default backtesting parameters.
*   `hunt_config.json` (12 lines, 439 bytes): Overrides and hyperparameters used to load teacher models.
*   `results.json` (653 bytes): Historic test outcomes and performance metrics.
*   `MODEL.md` (2,512 bytes): Design notes and model documentation.

### Core Design and Mechanics
Unlike naive signal averaging, which has historically diluted returns, `v72` performs a **hierarchical portfolio merge** using two teacher models:
1.  **Sniper Sleeve (`v71_live_confidence`):** Represents a high-win-rate, mean-reversion strategy.
2.  **Core Sleeve (`v39d_confluence`):** The return champion.

#### Merging Rules (Implemented in `signal_engine.py` lines 160–191):
*   **Sniper Only:** If the sniper model produces a long signal (`sn > 0`) and its confidence meets the minimum threshold (`sc >= sniper_min_conf`, default 0.0), its weight is selected and capped at `max_weight` (default 0.50).
*   **Core Only:** If only the core model triggers, the weight is scaled by `core_scale` (default 0.85) and capped at `max_weight`. An ordinal confidence value is computed based on core signal intensity: `core_conf = (0.45 + 0.45 * co).clip(0.35, 0.92)`.
*   **Both Active (Stacked):** If both trigger, `v72` takes the full sniper weight plus a fraction (`both_core_frac`, default 0.35) of the scaled core weight, capped under the per-symbol limit of 0.50 (hard-coded via `max_weight`). The composite confidence is a weighted average: `both_conf = (0.55 * sc + 0.45 * core_conf).clip(0.40, 0.95)`.

### Exported State
The model tracks the active trade allocation in:
*   `self.last_confidence`: Maps symbols to series of confidence values (0.0 to 1.0) for the live trade desk.
*   `self.last_sleeve`: Identifies active sleeves (0 = Flat, 1 = Sniper, 2 = Core, 3 = Both).

---

## 2. Implementation of `AlmgrenChrissGlobalEquityEngine`

### Location
*   **Engine Wrapper:** `tools/evolve/ac_execution.py` (108 lines, 3,982 bytes)
*   **Analytical Math:** `tools/impact_model.py` (151 lines, 5,199 bytes)

### Implementation Mechanics
`AlmgrenChrissGlobalEquityEngine` inherits from the standard `GlobalEquityEngine` (defined in `backtest.engines.global_equity`) and overrides the transaction cost function:

1.  **Rebalance Context Capture (lines 49–62):** Overrides `_execute_bars` and `_rebalance` to capture the current active timestamp, target weight, symbol, and total equity at rebalance time.
2.  **Slippage Application (lines 64–107):** In `apply_slippage(price, direction)`, it first computes the base fixed spread (`super().apply_slippage(price, direction)`).
3.  **Impact Calculation:**
    *   Estimates historical Average Daily Volume (ADV) and per-bar log-return volatility via helper functions in `impact_model.py` (`estimate_adv` and `estimate_volatility` using a rolling lookback of `ac_adv_days` and `ac_vol_days` respectively).
    *   Determines order size in shares:
        *   For closing/reducing trades: reads the size from `self.positions`.
        *   For opening trades: calculates `target_notional = abs(target_weight) * equity * leverage` and converts it to shares.
    *   Computes total impact using `impact_model.impact_per_share()`:
        $$\text{Temporary Impact} = \eta \times \left(\frac{\text{Shares}}{\text{ADV}}\right)^\beta \times \text{Volatility} \times \text{Price}$$
        $$\text{Permanent Impact} = \gamma \times \left(\frac{\text{Shares}}{\text{ADV}}\right) \times \text{Price}$$
        $$\text{Total Impact} = \text{Temporary} + \text{Permanent}$$
    *   Applies the impact: returns `base_slippage + direction * impact` (where `direction` is 1 for Buy, -1 for Sell).

### Configuration Options
Activated by specifying the following keys in `config.json` (or via `extra_cfg` in script calls):
*   `impact_model`: `"almgren_chriss"` (string, activates the engine)
*   `ac_eta`: temporary impact coefficient (default: `0.1`)
*   `ac_gamma`: permanent impact coefficient (default: `0.0`)
*   `ac_beta`: power-law exponent (default: `0.5`, square-root law)
*   `ac_adv_days`: average daily volume lookback (default: `20` trading days)
*   `ac_vol_days`: standard deviation lookback (default: `20` trading days)

---

## 3. Macro Features & Regime Classification Logic

### `tools/evolve/macro_features.py`
This module defines point-in-time macro, cross-asset, and long-memory features for use by meta-labelers.

1.  **Fractional Differentiation (lines 38–140):**
    *   Binomial expansion weights (`fracdiff_weights`) are used to apply $(1 - L)^d$ to price series causal-style.
    *   Estimates the $d$ parameter using either rescaled-range Hurst exponent ($d = H - 0.5$) or an Augmented Dickey-Fuller (ADF) grid search.
2.  **Macro Calendar and Surprises (lines 143–283):**
    *   Standardizes macro surprises (CPI, PPI, FOMC, NFP, GDP, ISM) relative to historical expanding standard deviation (`parse_macro_calendar`).
    *   Applies backward `merge_asof` joins on official release times (`release_ts`) to prevent forward leakage.
    *   Computes proximity countdowns: hours since the last release and hours to the next release.
3.  **Cross-Asset Metrics & Regimes (lines 288–397):**
    *   Computes rolling betas and correlations against SPY (market) and TLT (rates) using shifted returns.
    *   Risk regimes are computed via `regime_features()`:
        *   VIX level, VIX rolling z-score, VIX percentile.
        *   SPY SMA distance and 1H momentum.
        *   `risk_on_score`: average of Low VIX pct, SPY momentum, and rate-equity correlation flags.
4.  **Interaction terms (lines 438–479):**
    *   Interaction products: e.g. `macro_surprise * risk_on_score`, `macro_surprise * low_vix * high_beta_flag`.
5.  **Integration Pipeline (lines 621–674):**
    *   `MacroCrossAssetEngine` provides a clean `fit`/`transform` interface for out-of-sample walk-forward runs.

### `tools/institutional_flow/features.py`
This module computes microstructure-based point-in-time features from OHLCV data.

1.  **Order Flow Imbalance Proxy (`ofi_proxy`, lines 129–173):**
    *   Estimates aggressive buys/sells by blending candle direction (close vs open) with the tick rule (close vs prior close).
2.  **Wick Absorption (`absorption_score`, lines 176–219):**
    *   Measures stealth absorption: cumulative volume divided by price change over a lookback window, normalized by volume SMA and ATR.
3.  **Volume Schedule Deviation (`schedule_deviation`, lines 222–245):**
    *   Measures deviation of current intraday cumulative volume against a historical intraday schedule (built from prior days).
4.  **VPIN Toxicity (`vpin_proxy`, lines 248–292):**
    *   Bar-safe VPIN approximation: volume is bucketed into fractions of ADV; computes the rolling average imbalance across completed buckets.
5.  **Volume-Price Agreement (`vpa_confirmation`, lines 295–330):**
    *   A combination of volume z-score and close location relative to the bar range.
6.  **Regime Features (`regime_features`, lines 333–357):**
    *   Captures trend direction, price distance to rolling VWAP, volatility regime (ATR relative to its MA), and RSI.

---

## 4. Backtest Execution Infrastructure

### Backtest Runner (`backtest/runner.py`)
This is the fixed entry point for backtesting.
*   **Loading Configuration (lines 55–100):** Reads and validates `config.json` using the `BacktestConfigSchema` Pydantic model.
*   **Model Importing (lines 674–699):** Dynamically loads the `SignalEngine` from the run directory using `importlib` and instantiates it. Prior to loading, it performs AST checks (`_validate_signal_engine_source`) to prevent top-level execution side-effects or unsafe imports.
*   **Market Engine Instantiation (lines 774–780):** Retrieves the appropriate execution engine via `_create_market_engine()`. If it's a standard run, the routing handles OKX/CCXT -> `CryptoEngine`, Tushare -> `ChinaAEngine` or `GlobalEquityEngine`, and yfinance -> `GlobalEquityEngine`.

### Dynamic Model Ranker (`tools/dynamic_model_rank.py`)
Acts as a wrapper and orchestrator for running batch backtests across multiple universes.
*   **Monkeypatching (lines 41–77):** It imports `backtest.runner` and replaces the native `_create_market_engine` function with `_create_market_engine_for_local`.
*   **Interception:** If the backtest configuration has `config["impact_model"] == "almgren_chriss"`, `_create_market_engine_for_local` overrides the default engine and instantiates the `AlmgrenChrissGlobalEquityEngine`.
*   **Run Copying (lines 275–326):** In `run_one()`, it copies `signal_engine.py`, `config.json`, and all defined `DEPENDENCIES.json` files from the model source directory into the specific backtest run folder before triggering the runner via `backtest.runner.main()`.
