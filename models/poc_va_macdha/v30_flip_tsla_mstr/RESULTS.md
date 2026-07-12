# v30_flip_tsla_mstr — backtest honesty

## What this is
TSLA + MSTR, **long calls** on bounce days, **long puts** on dump days, hold **1–5 days**, **~70% of book** in premium, **no spreads**.

## Full window (2024-08 → 2026-07, $1M)
| Metric | Value |
|--------|-------|
| Return | **−61.7%** |
| Max DD | **−68%** |
| Trades | 770 fills |
| Win rate | ~36% |

**Automated full-period flip rules do not beat your discretionary edge.** Over-trades and 70% size turns losers into account damage.

## May–June 2026 (interesting)

On a warmed $1M path mid-drawdown (~$666k entering May):

| Month | Equity path | Month ret | Notes |
|-------|-------------|-----------|--------|
| **May** | ~$667k → ~$680k | **~+2%** | Mix of call bounces + some puts |
| **June** | ~$674k → ~$705k | **~+4.7%** | Strong MSTR put streak mid/late June |

So **spring 2026 short-hold call/put activity can print**, but it’s not the same as “+145k discretionary TSLA/MSTR.”

## $1k
Often **cannot open** size after first loss, or dies on first bad MSTR lot. Need enough for **1 short-dated lot** (~few hundred–$1k+ premium on TSLA/MSTR).

## Takeaway for live
1. Use v30 as a **signal style / scanner** (call day vs put day), not blind full-size auto on every bar.
2. Your edge is **when** you take the flip and **when you skip** — model can’t fully replace that yet.
3. Keep structure: **calls + puts only**, short hold, TSLA/MSTR — that part matches you.
