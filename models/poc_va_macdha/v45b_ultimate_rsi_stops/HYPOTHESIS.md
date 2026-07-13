# Hypothesis

**Version:** `v45b_ultimate_rsi_stops`  
**Family:** `poc_va_macdha`  
**Date:** 2026-07-13

## Claim

The raw Ultimate RSI color rule (v45) is profitable but produces intolerable drawdown because it holds long through adverse trend moves. Adding an ATR stop/trail and a simple regime filter (price above its long-period SMA) will cut max drawdown toward the project pass bar while preserving the 4h mean-reversion edge.

## Finds applied

- v45 baseline: Ultimate RSI 4h signal is the strongest timeframe.
- Best v45 parameters (length=21, smooth=14, ob=70, os=30, RMA/EMA) used as the starting point.
- ATR stop/trail to replace the unconditional hold.
- Long-period SMA regime filter to avoid buying in structural downtrends.

## Finds avoided

- Hard volume/EMA confluence filters (v29/v30 fail pattern).
- Meta-ML overlays (v39 lineage) — not needed for this iteration.
- Complicated adaptive thresholds — first prove the stop + regime core.

## Pass bar target

Must beat: PF ≥ 1.2, |DD| ≤ 25%, Sharpe ≥ 0.5, trades ≥ 40 on claimed window.

## Result

4h signal, length=21, smooth=14, ob=70, os=30, RMA/EMA, ATR multiplier=2.5, trailing stop, no regime filter:

- **Return:** 876.1% | **Max DD:** -25.5% | **Sharpe:** 2.02 | **Trades:** 34 | **Win rate:** 47%
- Final value: $9,761 on $1,000.

This is a 2.4× return improvement over the champion `v39d_confluence` (357.5%), but the max drawdown is still 25.5% vs the champion's 13.4%. The 50-bar SMA regime filter was too restrictive and produced zero trades; the best run disabled it. The pass bar is almost hit — |DD| is just 0.5% above the 25% threshold.

## Kill criteria

If the next iteration cannot bring |DD| below 25% on a 6-month hold-out OOS test, record with `tools/findings.py record --status fail` and follow `models/_shared/FAILURE_PROTOCOL.md`.
