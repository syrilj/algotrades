# Book Research Report — 2026-07-11

## Books read
1. Anna Coulling — Volume Price Analysis  
2. George Soros — Alchemy of Finance  
3. Dixit & Nalebuff — Thinking Strategically  
4. Options Strategies Quick Guide  

Extracts: `books/_extract/` · Mapping: `models/poc_va_macdha/v17_book_vpa/BOOK_INSIGHTS.md`

## Edges tested (new model sections)
| Version | Idea | Pass bar? | vs v15 winner |
|---------|------|-----------|---------------|
| `v17_book_vpa` | Full Coulling+Soros+commitment gates | YES | FAIL — Sharpe 1.62 vs 2.13; return cut in half |
| `v17b_book_vpa_light` | no_demand + commitment + stopping reclaim | YES | Mixed — **PF 2.88 > 2.68**, DD −9.6% vs −13.2%, but Sharpe/return still below |

## What worked
- Coulling **no-demand / commitment** filters improve trade *quality* (higher PF, lower DD).
- Stopping-volume reclaim is a useful alternate entry path (don’t only require confirm_up).

## What failed
- Stacking climax / topping / effort-ok on **1H** over-filters (v17). Those signals need daily/4H grain or softer thresholds.
- Book gates alone do **not** beat v15 meta capacity (fewer trades → lower total return/Sharpe).

## Applied to other model (`poc_va_gex`)
Script: `models/poc_va_gex/research/book_vpa_meta.py`  
Artifact: `models/poc_va_gex/artifacts/BOOK_VPA_META.json`

| Filter | OOS WR lift | Notes |
|--------|-------------|-------|
| `vol_z_ge2` | +27.6pp (n=11) | Still strongest GEX precursor |
| `vol_z_ge1` / `book_plus_volz1` | +22.9pp (n=29) | Book+volz ≈ volz alone |
| `not_no_demand` / `book_light` | +0.4pp (n=149) | Tiny standalone lift |

**GEX next step:** keep `vol_z` as primary meta; use Coulling no-demand as soft veto only, not a hard capacity killer.

## Verdict
Do **not** promote v17/v17b over `v15_meta_xgb`. Keep v15 as WINNER. Reuse light Coulling gates as optional risk overlays / GEX soft filters.
