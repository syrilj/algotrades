# v47_high_freq_edge

**Version:** `v47_high_freq_edge`  
**Family:** `poc_va_macdha`  
**Date:** 2026-07-13

## Claim

A high-frequency, long-only 1H mean-reversion edge can be extracted by buying Ultimate RSI pullbacks into the oversold zone and exiting quickly via a triple-barrier. The model is intentionally tuned for **high trade count** while keeping **profit >> risk**:

- **Primary signal:** Ultimate RSI color cross into the oversold zone (`os=30`, `ob=70`) on 1H bars.
- **Triple-barrier exit:** ATR(14) trailing stop (`2.5 × ATR`), RSI overbought cross (`70`), and a `max_hold_bars=8` vertical barrier.
- **Meta-sizing:** a rule-based confidence score is available (trend + volume), but the tuned production config leaves those filters off because they hurt the 1H oscillator edge.
- **Risk control:** the ATR stop and the 8-bar max hold are the primary risk controls; combined they cap the average losing trade and recycle capital.

## Rule

1. Compute Ultimate RSI on 1H close (`length=14`, `smooth=14`, `RMA` → `EMA` signal).
2. **Enter long** when the oscillator line crosses under `30` while not already in a position.
3. **Exit** on the first of:
   - oscillator crosses over `70` (green),
   - price closes at or below the trailing ATR stop (`2.5 × ATR` below the trade high),
   - `8` bars have elapsed since entry (vertical barrier).
4. Position size is `1.0` in the tuned run; `use_trend`/`use_volume` are disabled for this configuration.

## Parameters

- `signal_tf`: `1h`
- `length` / `smooth`: `14` / `14`
- `os_value` / `ob_value`: `30` / `70`
- `smo_type1` / `smo_type2`: `RMA` / `EMA`
- `atr_period` / `atr_smo`: `14` / `RMA`
- `atr_mult`: `2.5`
- `tp_atr_mult`: `2.5` (disabled via `use_tp: false`)
- `use_trail`: `true`
- `max_hold_bars`: `8`
- `use_trend`: `false`
- `use_volume`: `false`

## Pass bar target

On `EQUITY_WINNER_BAG` 2024-08-01 → 2026-07-11, `source=local`, `$1,000` scale:

- Trade count ≥ 200 (achieved: **306**)
- Total return positive (achieved: **306.6%**)
- Sharpe ≥ 1.0 (achieved: **1.68**)
- Max drawdown ≤ 25% (achieved: **21.8%**)

## Verified result

See `REPORT.md` for the full `final` tag backtest.

## Kill criteria

If the model cannot reproduce the `final` tag result on a fresh run (≥ 200 trades, Sharpe ≥ 1.0, positive return), follow `models/_shared/FAILURE_PROTOCOL.md`.
