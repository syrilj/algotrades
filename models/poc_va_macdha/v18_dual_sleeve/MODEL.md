# v18_dual_sleeve

**Status:** Research candidate from parallel feedback loops — **not promoted** (needs engine backtest + PASS_BAR).

## Idea
Two DNA paths in one book (do not merge into one vanity WR):

| Sleeve | Universe | Regime gate | Extra hard filters |
|--------|----------|-------------|--------------------|
| Sniper | APLD, IONQ | `gate_qqq_trend` | local MACD-HA green, vol expand, block red-flag |
| Large | TSLA, MU | `gate_qqq_and_mag7` | above SMA20 on signal TF, block red-flag |

## Trade-level proof (multiloop)
Source: `runs/poc_va_multiloop/artifacts/`

- Sniper combo `f_qqq_trend + f_local_macd_green`: n=11, train WR **100%**, test WR **100%** (thin — satellite only).
- Large Loop B `f_qqq_and_mag7 + f_not_red_flag`: n=16, WR 81%, OOS WR 71%, OOS exp **+4.9%**.
- Broad Loop C (prior path): n=29, OOS WR 83% — still **< PASS_BAR min_trades=40**.

## Honest limits
- Trade-level ≠ engine backtest. Promote only after full run clears PASS_BAR.
- Sniper n too small for sole winner.
- WINNER stays `v15_meta_xgb` until v18 proves out.
