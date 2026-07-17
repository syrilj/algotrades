# v64_crwv_bounce

## Problem
Global bag models (v39d etc.) print low confidence on CRWV during multi-week downtrends because their edge is HTF-trend + confluence continuation — not demand-zone mean reversion.

## Hypothesis
CRWV at multi-week lows with put-wall support (75/80) and call-flow into 85/90 produces **bounce trades** when local structure flips (HA green / stop-volume / VWAP reclaim), even if HTF is still mixed.

## Design
- Demand score vs VAL, 20d swing low, static put walls
- Soft bounce points (HA, vol confirm, mom, HTF bonus)
- HTF green **not required**
- Hard skip on dump / red-flag chase
- ATR stop + trail

## Not a promise
High specialist confidence means “levels + structure match bounce setup,” not “guaranteed bounce.” Invalidation is explicit (78.40 / 75).
