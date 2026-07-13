# Hypothesis

**Version:** `v45_ultimate_rsi`  
**Family:** `poc_va_macdha`  
**Date:** 2026-07-13

## Claim

The LuxAlgo Ultimate RSI oscillator’s color rule is a bounded, range-aware momentum measure that should produce profitable mean-reversion trades on high-beta US equities: go long when the line becomes red (crosses into oversold) and exit when it becomes green (crosses into overbought). Running the signal on a 4-hour bar should reduce noise and capture the larger swings that the 1-hour timeframe misses. The default 80/20 thresholds are too conservative; widening to 70/30 should increase trade frequency and return while the RMA smoothing on the oscillator preserves responsiveness.

## Finds applied

- New model, not a recombination of prior findings.
- Reuses the `poc_va_macdha` harness (`signal_engine.py` + `config.json`) and `dmr.run_one` for comparable cost assumptions.
- Honest mean-reversion entry: red = oversold, green = overbought.

## Finds avoided

- Hard volume/EMA confluence filters (v29/v30 fail pattern) — none applied.
- Meta-ML overlays (v39 lineage) — none applied.
- Pure price ML or climax stacking — none applied.

## Pass bar target

Must beat: PF ≥ 1.2, |DD| ≤ 25%, Sharpe ≥ 0.5, trades ≥ 40 on claimed window.

## Initial result

Baseline + staged grid on the EQUITY_WINNER_BAG ($1k, `source=local`, `interval=1H`, `2024-08-01` → `2026-07-11`):

- Best return: **255.6%**, DD **-59.3%**, Sharpe 1.16, 25 trades (ob=70, os=30, len=14, sm=14, RMA/EMA, 4h signal).
- Best risk-adjusted: **230.8%**, DD **-41.1%**, Sharpe 1.28, 26 trades (ob=70, os=30, len=21, sm=14, RMA/EMA, 4h signal).

**Status:** `working` — not pass-bar. The 4h timeframe is the clear winner, but drawdown is too large because the model has no protective stop and no regime filter. The next iteration must add an ATR stop/trail and a trend filter.

## Kill criteria

If OOS fails to bring |DD| below 25% or Sharpe below 0.5 after the ATR-stop + regime-filter iteration, record with `tools/findings.py record --status fail` and follow `models/_shared/FAILURE_PROTOCOL.md`.
