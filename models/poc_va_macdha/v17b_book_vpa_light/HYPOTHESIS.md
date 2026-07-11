# Hypothesis

**Version:** `v17b_book_vpa_light`  
**Family:** `poc_va_macdha`  
**Date:** 2026-07-11

## Claim

v17 full book stack cut DD but also cut return/Sharpe vs v15 (over-filter). This ablation keeps only the highest-signal Coulling/commitment rules: `block_no_demand`, `require_commitment`, `allow_stopping_reclaim`. Drops noisy 1H climax/topping/effort gates that likely false-positive on hourly bars.

## Kill criteria

If still worse than v15 on Sharpe without DD benefit → fail finding; port only `block_no_demand` into GEX volume-z meta as a soft filter.
