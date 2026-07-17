# v60_microstructure

**Microstructure-grounded high-precision long model with OHLCV-safe order-flow, absorption, schedule-deviation, and VPIN-style features.**

## Components

- **signal_engine.py** — self-contained `SignalEngine` that computes point-in-time microstructure features, runs an XGB classifier (or a calibrated heuristic fallback), and emits target positions with a state-machine for stop-loss, take-profit, max-hold, and trend/VWAP invalidation.
- **tools/train_v60_microstructure.py** — fetches `source=local` 1H data, computes triple-barrier labels, and trains an XGBClassifier saved to `meta_xgb_final.json`.
- **hunt_config.json** — model hyperparameters and risk controls.
- **meta_config.json** — feature list and XGB threshold.

## Feature module

All features are computed from OHLCV only and are point-in-time (no future leakage).

| feature | economic meaning | leakage check |
|---------|-------------------|---------------|
| `ofi` | EMA of signed-volume imbalance (candle delta + tick rule) | uses current bar only; shifted by runner |
| `ofi_persistence` | rolling sum of OFI proxy | same window, no forward look |
| `absorption` | signed volume per unit price move, normalised by ATR and volume | past-only |
| `schedule_dev` | cumulative intraday volume vs historical TWAP-like profile | profile mean over prior days, shifted by 1 |
| `vpin` | volume-bucketed average absolute imbalance | bucket built sequentially |
| `vol_z` | volume z-score | past-only rolling |
| `vpa_confirmation` | volume-price agreement (close location × volume) | current bar |
| `trend` | close > SMA(200) | past-only |
| `above_vwap` | close > rolling VWAP(50) | past-only |
| `vol_regime` | ATR% > its rolling average | past-only |
| `rsi` | RSI(14) | past-only |
| `dist_vwap_pct` | distance to VWAP | past-only |
| `return_*` | lagged returns | shifted by 1, 4, 24 bars |
| `hour` / `day_of_week` | time effects | known at bar close |

## Risk management

- **Stop-loss:** `entry × (1 - max(0.5%, sl_atr_mult × ATR%))`
- **Take-profit:** `entry × (1 + max(1.0%, tp_atr_mult × ATR%))`
- **Max hold:** `max_hold_bars` bars
- **Invalidation:** close below VWAP(50) or trend SMA(200) broken
- **Position sizing:** `signal_scale` (1.0 = full target weight; runner normalises across symbols)

## Results

Full-history (in-sample) on `source=local` 1H WINNER bag (2024-08-01 → 2026-07-11, $1,000):

- `v60_microstructure`: **+639.4% return**, **-21.8% max DD**, **Sharpe 2.69**, **105 trades**, **62% win-rate**, **final $7,394**

Walk-forward OOS (train 2024-08-01 → 2025-08-01, test 2025-08-01 → 2026-07-11, $1,000):

- `v60_microstructure`: **+14.8% return**, **-13.7% max DD**, **Sharpe 0.26**, **13 trades**, **38% win-rate**, **final $1,148**

## Note

This is an **in-sample artifact** until validated with a true hold-out or paper-trading window. The OHLCV proxies are lossy relative to tick/signed-trade data; the model is retained for research, not promoted to production.
