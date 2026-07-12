# Hypothesis — v39c_live_tight

**Parent:** `v39b_live_adapt` (WINNER)  
**Date:** 2026-07-12

## What we fixed in the v39 line (so you know)

| Version | Change | Result |
|---------|--------|--------|
| v39 | Full continuous Coulling, hard-ish size cuts | Quality↑ capacity↓ (fail promote) |
| **v39b** | Light negatives, no floor, fast look, mom/regime, live streak | **+365% / 2.77** beat v38 |
| **v39c** | Dual-speed VPA blend + soft DD ATR cut + milder mid-trade shrink | Recover early lag, keep late edge |

## v39c claim

Blend **fast (look=3)** and **slow (look=5)** Coulling scores by `vol_regime` so quiet markets don’t over-react (early holdout was slightly behind v38) while loud markets stay fast. Add soft size cut when ATR expanded and VPA weak. Milder mid-trade shrink to avoid over-exiting winners.

## Pass if

Beats or matches v39b on full Sharpe **or** improves early Sharpe toward v38 without losing late return edge; PASS_BAR clear.
