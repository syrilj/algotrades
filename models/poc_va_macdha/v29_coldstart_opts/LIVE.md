# LIVE playbook — v29_coldstart_opts (**OPTIONS DEFAULT**)

**Status:** OOS champion (2026-07-12). Beat prior default `v22_opts_live` on pure holdout aggregate.

See: `OPTIONS_WINNER.json`, `runs/poc_va_v29_oos_challenge/REPORT.md`.

## What to trade
Long **ATM ~21 DTE calls** when v21 side DNA fires on:
**IONQ, AVGO, HOOD, MU**

## Risk
- ≤**10%** equity in premium per new entry
- Skip entry if signal strength **&lt; 0.35**
- Halt new entries at **30%** peak DD; flatten at **45%**
- **Surgical only:** no new risk on FOMC day **and** elevated VIX
- Macro fail-open (if VIX feed dies, still trade)

## Why this beat v22 (unseen)

| | mean OOS score | mean OOS ret | mean OOS DD |
|--|----------------|--------------|-------------|
| **v29 (promoted)** | **0.028** | **+1.4%** | −6.5% |
| v22 21 DTE | 0.018 | +0.4% | −5.4% |

### What helped
1. **Correct DTE in premium sizing** (v22 used implicit 30d estimate)
2. **Min signal 0.35** (skip weak entries)
3. **Surgical FOMC∧VIX** (fail-open macro)

### What did **not** help OOS mean score
- 5d cooloff + loss streak half-size (won more folds but **worse mean score**)

## Full-window reference (not for promotion alone)
| | ret | DD | Sharpe | WR |
|--|-----|-----|--------|-----|
| v29 | **+66.5%** | −11.5% | 1.25 | 82% |
| v22 | +59.8% | −11.2% | 1.28 | 82% |

## Honest goal check
Cold-start OOS edge is still modest. Not a $1k→$1M guarantee. This is the best **unseen-validated** options default in the bag.

## Re-challenge
```bash
.venv/bin/python tools/oos_challenge_v29.py
```
