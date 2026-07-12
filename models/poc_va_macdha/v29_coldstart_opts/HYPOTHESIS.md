# v29_coldstart_opts — **promoted OOS default**

## Result

| Test | Winner |
|------|--------|
| Pure OOS aggregate mean score | **v29 surgical config** (0.028) beats v22 (0.018) |
| Full-window reference | v29 +66.5% vs v22 +59.8% |
| Full stack (cooloff+streak) | **Rejected** — worse mean OOS despite 3/5 fold wins |

## Design (from findings)

Built on **v22 cold-start DNA** only:

- PRIMARY: v21 side (untouched)
- 21 DTE ATM calls, 10% risk, halt 30% / flatten 45%
- **No conf-tier** (lost OOS historically)
- **No broad narrative**
- Surgical `fomc_day ∧ vix_elevated` only
- `min_size_frac=0.35` skip weak signals
- Premium uses **actual 21 DTE** (fixes v22 sizing bug using 30d default)

## Ablation (pure OOS)

| Variant | mean OOS score | Notes |
|---------|----------------|-------|
| **v29_surgical_only** | **0.028** | **promoted** |
| v29_cooloff_only | 0.028 | tied; cooloff rarely fired same as surgical path |
| v22_21dte | 0.018 | prior default |
| v26_14dte | 0.007 | |
| v29_coldstart full | 0.002 | cooloff+streak hurt mean |

## Artifacts

- `runs/poc_va_v29_oos_challenge/CHALLENGE.json`
- `runs/poc_va_v29_oos_challenge/REPORT.md`
- `runs/poc_va_v29_promote/` full-window pair
