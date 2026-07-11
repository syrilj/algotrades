# Hypothesis

**Version:** `v18_wr90`  
**Family:** `poc_va_macdha`  
**Date:** 2026-07-11  
**Target:** win rate ≥ 90% with strong Sharpe on a sniper sleeve

## Claim

Combine WORKING findings into a selective sleeve (not full 6-name book):
- v16 path: APLD+IONQ only + QQQ trend + vol_expand + block_red_flag (already 83% WR)
- Book: Coulling commitment + no-demand block
- GEX meta: prior-day `vol_z >= 1`
- Trade desk: price above EMA200
- Soft confidence floor 0.72

Expect very few trades. Pass only if WR≥90% AND PF≥1.2 AND |DD|≤25% AND Sharpe≥0.5. If trades < 10, mark as exploratory sleeve (sample_noise risk).

## Finds applied
- book_vpa_light, volume_meta vol_z, research_buckets small-cap, structure EMA200, v16_wr80 universe

## Finds avoided
- Full 1H climax/effort stack (v17 fail)
- Expanding universe to TSLA/MU/ARM/SPY (blocked 80% before)
