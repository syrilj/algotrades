# RESEARCH_NEXT — after book VPA loop (2026-07-11)

Feed this into the next improve iteration. Source findings: `models/_shared/findings.jsonl` (grep `book_`).

## Keep as WINNER
- `v15_meta_xgb` remains WINNER (best Sharpe/return capacity).

## WORKING findings to apply next
1. **Light Coulling overlay** (`block_no_demand` / commitment / stopping_reclaim) → quality↑ (PF/DD), capacity↓. Prefer **soft size-down** on no_demand rather than hard block.
2. **GEX path:** `vol_z>=1` or `>=2` is the durable volume meta; Coulling no-demand is only a soft veto beside it (`BOOK_VPA_META.json`).
3. Architecture locked: primary rules → side; meta → whether/how much. Books do not replace primary with price ML.

## FAILED — do not repeat
1. Full 1H stack: `block_buying_climax` + `block_topping_volume` + `require_effort_ok` together (`v17_book_vpa`).
2. Promoting a quality-only filter that cuts trades enough to lose Sharpe vs winner.

## Next lake (pick ONE)
| ID | Experiment | Pass if |
|----|------------|---------|
| A | `v18_soft_nodemand`: v15 + size×0.5 when no_demand else full; no new hard gates | Sharpe ≥ v15−0.1 AND PF ≥ v15 AND DD ≤ v15 |
| B | Climax/effort gates on **4H/1D only** (not 1H) as soft exit, not entry block | Same bar + fewer climax chase losers |
| C | `poc_va_gex` wire: meta size from `vol_z` (+ optional soft no_demand) on existing primary | OOS WR/exp lift > 0 on walk-forward |
| D | Grow `v18_wr90` sleeve: more under-owned small-caps + longer window toward durable WR≥90 | WR≥90 with n≥40 OOS; else keep 83% sleeve |

## Avoid
- Stacking more vanity WR filters to force 90% on n&lt;10
- Promoting sniper sleeve over v15 for full-book Sharpe
- Retraining meta feat_cols until a soft-gate version beats v15 on Sharpe

## Artifacts
- `models/poc_va_macdha/v17b_book_vpa_light/REPORT.md`
- `models/poc_va_macdha/v17_book_vpa/BOOK_INSIGHTS.md`
- `models/poc_va_gex/artifacts/BOOK_VPA_META.json`
- `books/_extract/` (PDF keyword extracts)
