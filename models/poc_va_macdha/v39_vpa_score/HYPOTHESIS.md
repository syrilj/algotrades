# Hypothesis

**Version:** `v39_vpa_score`  
**Family:** `poc_va_macdha`  
**Parent:** `v38_research_stack` (WINNER)  
**Date:** 2026-07-12

## Claim (one paragraph)

Do **not** predict price. **React** to where smart money already parked inventory (volume-profile nodes: VAL / POC / VAH as supply–demand zones), then let **continuous Coulling VPA** tell us whether volume agrees with the reaction, and use **EMA cloud** only as path-of-least-resistance context for soft size. Primary SIDE stays frozen from specialist DNA (POC/VA + HTF). Secondary only: map a continuous `vpa_score` to size mults (boost stopping reclaim / no-supply tests / springs / confirm_up; cut no-demand / climax / effort anomaly / upthrust), mild boost when reacting at demand nodes with non-negative VPA, EMA bull/bear soft mult, and soft exit into climax when unarmed. Price can be manipulated; volume is harder to fake — so VPA is the truth filter, not a new side model.

## Why this should beat v38

| v38 | v39 |
|-----|-----|
| Binary soft VPA (no_demand ×0.62, commitment ×1.08, stop reclaim ×1.10) | Continuous score → graded size (0.42–1.22) |
| No explicit no-supply test after absorption | Book path: stop → no-supply test boost |
| No climax soft exit | Soft exit when climax_recent + weak score (unarmed only) |
| Structure only | Structure + demand-node proximity reaction |

## Finds applied

- B1 no_demand soft (graded, not binary)
- B2 commitment / stopping reclaim
- B3 stopping reclaim path
- B4 quality↑ capacity↓ only via soft size
- B6 don’t chase buying climax
- FAIL F1: **no** full 1H hard climax+topping+effort stack

## Finds avoided

- Price ML primary (`poc_va_xgb`)
- Hard VPA entry ANDs that killed Sharpe in `v17_book_vpa`
- Promoting PF/DD-only without beating winner Sharpe

## Pass bar

Must beat **v38** on same 1H window (2024-08→2026-07 style):

- PASS_BAR gates (PF ≥ 1.2, |DD| ≤ 25%, Sharpe ≥ 0.5, n ≥ 40)
- **Promote if:** Sharpe ≥ v38 − 0.05 **and** (return ≥ v38 **or** DD better with Sharpe ≥ v38 − 0.02)
- Kill if: trade count collapses >30% with no Sharpe gain, or OOS holdout fails

## Kill criteria

If continuous score over-cuts capacity like hard filters → fall back to v38 binary soft VPA; keep only `no_supply_test` + climax soft-exit ablation.
