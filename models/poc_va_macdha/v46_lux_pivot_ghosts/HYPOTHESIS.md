# v46_lux_pivot_ghosts

**Version:** `v46_lux_pivot_ghosts`  
**Family:** `poc_va_macdha`  
**Date:** 2026-07-13

## Claim

The LuxAlgo "Pivot Points High Low & Missed Reversal Levels" indicator can be used as a structural trend-follow signal. Two variants are tested:

1. **Zig-zag trend-follow:** the latest confirmed pivot defines the current leg. Long after a confirmed pivot low, flat after a confirmed pivot high.
2. **Missed-level S/R confirmation:** only enter long when a confirmed pivot low is a **higher low** (close above the new swing low) and exit when a confirmed pivot high is a **lower high** or the close falls below the previous swing low.

## Rule

- Detect `ta.pivothigh(pivot_length, pivot_length)` and `ta.pivotlow(pivot_length, pivot_length)` events (confirmed `pivot_length` bars after the pivot).
- Mode `zigzag` (default): go long on a pivot low, exit to flat on a pivot high.
- Mode `missed_sr`: enter long when a pivot low is a higher low and the close is above it; exit on a lower-high pivot or on a close below the previous swing low support.
- Optional ATR stop/trail can be added in `zigzag` mode via `use_atr_stop`, `atr_mult`, `use_trail`, `atr_period`.

## Parameters

- `strategy_mode`: `"zigzag"` or `"missed_sr"` (default `"zigzag"`).
- `pivot_length`: 10, 20, 50 (default 10).
- `signal_tf`: resample frame for pivot detection (e.g. `None`, `2h`, `4h`, `1D`; default `None` — uses the native interval).
- `use_atr_stop`, `atr_mult`, `use_trail`, `atr_period`: optional risk controls in `zigzag` mode.

## Pass bar target

Must return a positive total return, with Sharpe > 0.5 and a maximum drawdown below 30% on the `EQUITY_WINNER_BAG` over 2024-08-01 → 2026-07-11. Useful comparison bars are the champions `v39d_confluence` (357.5% ret, -13.4% DD, Sharpe 2.82) and `v45b_ultimate_rsi_stops` (876% ret, -25.5% DD, Sharpe 2.02).

## Kill criteria

If the best parameter set cannot produce a positive return or a Sharpe > 0.3 on a 6-month OOS window, follow the project `FAILURE_PROTOCOL.md`.
