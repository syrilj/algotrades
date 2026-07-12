# LIVE playbook — v35_softstruct_bag8 (**OPTIONS DEFAULT**)

**Status:** OOS champion (2026-07-11 late loops, round 2). Supersedes v34_bag6_opts.
Built by composing every finding from this loop cycle: v29's robust shell (surgical block,
10% premium cap, DD halts) + v32's soft-structure **sizing** overlay (the only part of its
growth DNA that survives cold start) + the widest OOS-surviving bag.

## What to trade

Long **ATM ~21 DTE calls** when the signal DNA fires on:
**IONQ, AVGO, HOOD, MU, TSLA, GME, COIN, RKLB**

Size per entry = signal × narrative × structure:
- structure **good** (EMA 8/21/55 cloud bull ∧ above VAL/POC support ∧ room ≥ 0.4% to next node): size ×**1.15**
- structure **weak**: size ×**0.55** (this downsizing is what makes the wide bag safe — bag8 *without* it fails OOS at −0.039)

## Risk (unchanged — escalations are dead, retested twice)

- ≤ **10%** of equity in premium per new entry, min signal 0.35
- Surgical block only: FOMC day ∧ elevated VIX (fail-open)
- Halt new entries at **30%** peak DD; flatten at **45%**
- No naked shorts

## Election numbers (pure 5-fold OOS + full window)

| model | mean OOS score | mean OOS ret | full ret | full DD | Sharpe | WR | yrs→1000x @CAGR |
|-------|---------------|--------------|----------|---------|--------|----|-----------------|
| **v35_soft_bag8** | **0.1458** | **10.2%** | **+73.0%** | −9.1% | **1.78** | 86% | **24.5** |
| v34_bag6 (prior) | 0.1018 | 5.2% | +66.0% | −7.8% | 1.59 | 85% | 26.5 |
| v29 (grandparent) | 0.0282 | 1.4% | +63.0% | −13.2% | 1.20 | 75% | 27.5 |

Fold wins: 4/5 vs both v29 and v34. Sensitivity: weak-mult 0.55→0.70 ⇒ OOS 0.1505 / full +73.8% (not knife-edge).

## Honest caveats

- **wf_fold3 (2026H1) is its one lost fold** (+4.9% vs v34's +13.9%, DD −15.0%): the newest regime favors the narrow bag. Watch live fills; if 2026H2 keeps favoring bag6 names, v34 remains a valid fallback.
- The two big OOS wins (2025 folds, +21% each) overlap in calendar — closer to one independent observation than two. Mitigants: wins spread across TSLA/RKLB/IONQ/GME (4 fills each), and the full-window path (which contains 2026H1) also wins.
- ~20 variants have now been scored against these same 5 folds this cycle — selection pressure on the folds is real. This pick was 1 of 4 a-priori variants in its round, wins by a wide margin, and passed a sensitivity perturbation; still, treat live paper fills as the true holdout.
- Same premium-model limits as v22/v29 (BS estimate IV 0.55, crude mtm marking — FINDINGS #7 open).

## Growth sleeve (optional)

70/30 v35_soft_bag8 + v32_soft_strong, monthly rebalance: OOS 0.1140 (4/5 folds), **+85.7%** full-window,
DD −6.5%, ~21.7 yrs→1000x pace. soft_strong alone still fails OOS — never unblended.

## $1k → $1M check

At this model's full-window CAGR (~32%/yr): **~24.5 years**; growth sleeve ~21.7. At measured cold-start
OOS edge: several decades+. Still no honest configuration that reaches 1000x in single-digit years —
every leverage/sizing escalation tested this cycle failed the OOS gate.

## Artifacts

- Election: `runs/poc_va_v33_loops/inline/RESULTS_INLINE.json` (+ `BLEND_RESULTS.json`)
- Engine build: `runs/poc_va_v33_loops/inline_engines/v35_softstruct/` (ported from v32 soft_struct ablation)
- Prior: `v34_bag6_opts/`, `v29_coldstart_opts/`, `v22_opts_live/`
