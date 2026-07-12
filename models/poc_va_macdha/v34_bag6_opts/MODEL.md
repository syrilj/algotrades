# v34_bag6_opts — options default (elected 2026-07-11 loops)

**Engine:** identical to `v29_coldstart_opts` (21 DTE ATM calls, 10% premium/entry, surgical FOMC∧VIX block, halt 30% / flatten 45% DD, min signal 0.35, no cooloff).
**Change vs v29:** bag expanded IONQ/AVGO/HOOD/MU → **+ TSLA + GME** (config-only; OOS re-rank per FINDINGS rule "no silent symbol add").

## Why promoted

Pure OOS 5-fold challenge (same protocol/score as v29 election; harness reproduced v29's
CHALLENGE.json rows exactly before any experiment ran):

| model | mean OOS score | mean OOS ret | mean OOS DD | fold wins vs v29 | full ret | full DD | Sharpe | WR | n |
|-------|---------------|--------------|-------------|------------------|----------|---------|--------|----|---|
| **v34_bag6 (this)** | **0.1018** | **5.24%** | −9.15% | 3 wins / 2 exact ties | **+66.0%** | **−7.8%** | **1.59** | **85%** | 26 |
| v29_surgical_only (prior champ) | 0.0282 | 1.4% | −6.5% | — | +63.0% | −13.2% | 1.20 | 75% | 24 |

GME flips both bleeding 2025 cold-start folds (−5% → +4–7%); TSLA adds full-window growth
(+66% vs +46% for the GME-only bag). The two "losing" folds are exact ties (new names traded 0 times there).

## Variants on the frontier (all in runs/poc_va_v33_loops/inline/RESULTS_INLINE.json)

| variant | mean OOS score | full ret | yrs→$1M @ full CAGR | role |
|---------|---------------|----------|--------------------|------|
| v29_bag_gme_dte30 | **0.1170** (max) | +42.6% | 37.8 | max-robustness satellite |
| v29_bag6_dte30 | 0.1068 | +58.8% | 29.1 | robustness lean |
| **v34_bag6 (default)** | 0.1018 | +66.0% | 26.5 | balanced default |
| blend 70/30 bag6+soft_strong | 0.0757 (4/5 folds) | +80.5% | 22.7 | growth sleeve |
| blend 50/50 bag6+soft_strong | 0.0659 (4/5 folds) | +90.1% | 20.9 | growth sleeve |
| blend 30/70 bag6+soft_strong | 0.0520 (4/5 folds) | +99.6% | 19.4 | max growth that still holds 4/5 folds |

## Killed this loop (do not repeat; see findings.jsonl)

- **v32 soft_struct/strong fail OOS** (score −0.002/0.009, 2/5 folds) — +108–113% full-window growth is path-dependent.
- **risk_pct scaling dead**: 15–20% premium/entry REDUCES growth (equity-budget depletion) and craters OOS (r20 mean −0.0285). 10% is the max survivable.
- **vol_z boost sizing** (0.0195) and **fractional-Kelly sizing** (0.0169) both fail the OOS gate.
- otm5 / bag_tsla-alone: no improvement.

## Caveats (honest)

- Folds overlap (holdout_post_discovery contains wf_fold1-3 range) → fewer truly independent observations than 5.
- Small samples: 8–14 fills/fold; GME contributes 4 trades in the window.
- Premium model is BS-estimate (IV 0.55 fixed), crude 0.5·Δspot mtm marking — same limitation as v22/v29 (FINDINGS #7).
- $1k→$1M timing: at full-window CAGR (~30%/yr) ≈ 26.5 years; at measured cold-start OOS edge (~6–7%/yr) ≈ a century. The blends shorten the full-window pace to ~19–21 years. **No configuration tested reaches $1M from $1k in months/years-single-digits without accepting near-certain ruin** — that claim died in the risk sweep (see r20 fold3: −19.3% DD, OOS score negative).

## Reproduce

```bash
VIBE_TRADING_DATA_CACHE=1 .venv/bin/python -c "from pathlib import Path; from backtest.runner import main; main(Path('runs/poc_va_v33_loops/inline/full_window/v29_bag6').resolve())"
# fold sweep driver (a-priori variant registry preserved):
VIBE_TRADING_DATA_CACHE=1 .venv/bin/python runs/poc_va_v33_loops/inline_driver.py
# dual-sleeve blends:
.venv/bin/python runs/poc_va_v33_loops/blend_sleeves.py
```
