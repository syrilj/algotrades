# v30_feedback_pro — v28 + soft structure reaction (FAILED - use v32 instead)

**Status:** BLOCKED - same hard-filter pattern as v29  
**Real v30 results (2026-07-12):** +84.3% return, DD -13.3%, Sharpe 1.25, 36 trades  
**v28 baseline:** +74.5% return, DD -15.5%, Sharpe 1.17, 24 trades

## Key Finding: Hard filters kill performance

The hard volume surge + EMA200 filters reduced v28's win rate from 75% to 67% while only slightly improving DD. The correct approach (v32) is **soft sizing**:

- `structure_good` → size ×1.15
- `chase_ob` → size ×0.40 (soft, not blocked)
- `macd_os + ha_green` → size ×1.12 boost
- Adaptive DTE 10/14 based on vol percentile

Delete this version - **v32_soft_react_opts is the promoted winner** (+108% return, Sharpe 1.49).