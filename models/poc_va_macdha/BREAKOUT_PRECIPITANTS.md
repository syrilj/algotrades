# What actually precipitates breakouts

**Date:** 2026-07-11  
**Use in:** `tools/trade_desk.py` live desk (not yet a new backtest version)

## Stack (priority order)

| Priority | Signal | Role |
|----------|--------|------|
| 0 | **Sector rotation** | Which pond — money flow vs SPY (keep) |
| 1 | **Volume** | Whether a breakout is real |
| 2 | **22 EMA** | Drawdown / pullback buy zone inside an uptrend |
| 3 | **200 EMA** | Structural regime — loss = broken structure |

Sector rotation alone does **not** time entries. It only narrows the universe.

## Volume (main thing)

Breakouts fail when price clears a level on **dying** participation.

- **Surge (fuel):** relative volume ≳ 1.35× SMA20, or expand+rising, or confirm_up with rvol ≳ 1.1 → required for `BUY BREAKOUT`
- **Awake:** rvol ≳ 1.0 or volume rising → enough for `BREAKOUT WATCH` (alert only)
- **Dry / red-flag:** price up while volume falls → **AVOID** (trap)
- **Healthy dip:** price down + volume drying → good for 22 EMA / value pullbacks

Rule of thumb: **ignore a quiet drift through a level; only take volume-led breaks.**

## 22 EMA (drawdowns)

In an intact uptrend (above 200), pullbacks that **tag the 22 EMA** with quiet volume are the preferred long dip — better R:R than chasing highs.

- Near 22 from above + 200 intact → `PULLBACK ZONE` / best classic entries
- Loss of 22 after a breakout → tighten / re-evaluate (failed continuation)

## 200 EMA (structure)

- **Above 200:** structure intact — longs allowed
- **Below 200:** `AVOID (structure broken)` — don’t buy dips
- **Exception:** reclaim of 200 **with volume surge** (structural repair)

## Desk actions mapped

| Action | Precipitant |
|--------|-------------|
| BUY NOW | Classic value/POC setup; best when also near 22 |
| BUY BREAKOUT | Level break **+ volume surge** + 200 intact |
| BREAKOUT WATCH | Near highs, volume waking — wait for surge |
| PULLBACK ZONE | Extended or waiting on 22 / value |
| AVOID (structure broken) | Lost 200 without volume reclaim |
| AVOID | Dry volume on a push |

## Next research (backtest)

Hypothesis for a future `v17_*` engine: gate breakout entries on `vol_surge` + `above_ema200`; prefer adds/entries on `near_ema22` + `healthy_pull`. Promote only if OOS Calmar/PF clear `PASS_BAR.json` — not win-rate alone.
