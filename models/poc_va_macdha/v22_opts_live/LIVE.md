# LIVE playbook — v22_opts_live (SUPERSEDED)

> **Superseded 2026-07-11 late loops:** options default is now
> `models/poc_va_macdha/v34_bag6_opts/` (v29 engine + TSLA/GME bag, mean OOS score
> 0.1018 vs v22's 0.018). See `v34_bag6_opts/LIVE.md` and `OPTIONS_WINNER.json`.

**Status:** was OOS champion (2026-07-12). Elected by pure holdout + walk-forward, not full-window feedback score.

See: `models/poc_va_macdha/OPTIONS_WINNER.json`, `runs/poc_va_oos_rank/FINDINGS.md`.

## What to trade
Long **ATM ~21 DTE calls** when the signal DNA fires on:
**IONQ, AVGO, HOOD, MU**

## Risk / compound
- ≤**10%** of equity in premium per new entry
- Halt new entries at **30%** peak DD
- Flatten at **45%** DD
- No naked shorts

## Why this is the default (not v28)
| Test | Winner |
|------|--------|
| Full-window feedback loop | v28 surgical+cooloff (+104%) |
| **Pure OOS aggregate (promotion)** | **v22 21 DTE** (3/5 fold wins, best mean score, best mean DD) |

v28’s full-window edge is path-dependent (2024 compound + cooloff → HOOD). Cold-start OOS windows do **not** keep that ranking — so live default stays **v22**.

## Honest OOS snapshot (mean across 5 pure folds)
| | |
|--|--|
| Mean OOS return | ~+0.4% |
| Mean OOS DD | ~−5.4% |
| Note | 2025 cold-start folds are often flat/red for **all** contenders — small sample |

## Full-window reference (same bag)
Historical hunt numbers still useful for capacity; do not use alone for promotion.

## Honest goal check ($1k → $1M)
Not reliable in ~2 years at this measured OOS edge. This is the **most robust** options book under holdout stress, not a lottery ticket.

## Hunt / OOS artifacts
- `runs/poc_va_opts_hunt/artifacts/SYNTHESIS.md`
- `runs/poc_va_oos_rank/OOS_RANKING.json`
- `runs/poc_va_oos_rank/FINDINGS.md`
