# LIVE playbook — v34_bag6_opts (SUPERSEDED — now fallback)

> **Superseded same night (loops round 2):** default is now
> `models/poc_va_macdha/v35_softstruct_bag8/` (OOS 0.1458 vs 0.1018, +73% vs +66%).
> v34 remains the designated FALLBACK — it won wf_fold3 (2026H1), v35's one lost fold.

**Status:** OOS champion (2026-07-11 loops). Supersedes v29_coldstart_opts / v22_opts_live.
Elected by the same pure 5-fold OOS challenge that elected v29; beats it 0.1018 vs 0.0282 mean score
with 3 fold wins + 2 exact ties, and better full-window growth, DD, Sharpe, and WR.

## What to trade

Long **ATM ~21 DTE calls** when the signal DNA fires on:
**IONQ, AVGO, HOOD, MU, TSLA, GME**

## Risk / compound (unchanged from v29 — risk scaling was tested and is DEAD)

- ≤ **10%** of equity in premium per new entry (15–20% tested: less growth, much worse OOS)
- Skip entries when signal < 0.35 (quality floor)
- Surgical block only: FOMC day ∧ elevated VIX (fail-open if macro feed dies)
- Halt new entries at **30%** peak DD; flatten book at **45%** DD
- No naked shorts

## Optional growth sleeve (only if you accept more path risk)

Split equity **70/30 or 50/50** between this default and `v32 soft_struct_strong`
(runs/poc_va_v32_ablations/soft_struct_strong/), rebalanced monthly:
+80–90% full-window vs +66%, DD −6.6…−7.2%, still 4/5 OOS fold wins — but the
soft_strong sleeve **alone** fails OOS, so never run it unblended.

## Honest goal check ($1k → $1M)

| assumption | pace to $1M |
|------------|-------------|
| full-window CAGR repeats (~30%/yr) | ~26.5 years |
| 50/50 growth blend CAGR repeats | ~21 years |
| measured cold-start OOS edge (~6–7%/yr) | ~a century |

Shortest-time-to-$1M claims from leverage ledgers (10–15x) were re-tested this loop:
every sizing escalation (risk 15–20%, vol_z boost, Kelly) **failed the OOS gate**.
This book is the fastest honest compounder found so far, not a lottery ticket.

## Artifacts

- Election data: `runs/poc_va_v33_loops/inline/RESULTS_INLINE.json` + `BLEND_RESULTS.json`
- Frontier + kills: `models/poc_va_macdha/v34_bag6_opts/MODEL.md`
- Prior champs: `models/poc_va_macdha/v29_coldstart_opts/`, `v22_opts_live/`
