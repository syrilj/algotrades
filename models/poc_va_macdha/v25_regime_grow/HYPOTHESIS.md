# Hypothesis — v25_regime_grow

**Version:** `v25_regime_grow`  
**Family:** `poc_va_macdha`  
**Date:** 2026-07-11

## Claim

The path to grow a small book is **not** more entry filters. It is **vehicle + risk regime**:

1. **SIDE** stays the proven WINNER stack (`v23_devin_overlay` = v20b + vol-z conviction overlay).
2. When there is **no A+ options setup**, park risk in **equities** (same side rules, half-Kelly) so capital is not idle and not forced into theta lottery.
3. When conviction clears the **attack bar** (model conf + vol_z + QQQ + macro), switch to **options** and size **aggressively within a hard max-loss cap** (debit spreads preferred).
4. **Cut losers fast** on options (≤ −30% premium, stagnant 2 sessions, force flat ≤5 DTE) so dead risk frees capital for the next A+ play.
5. Portfolio **DD throttle / halt / flatten** keeps the $1k→$1M path alive (v24’s −71% DD is not live-acceptable).

Feedback loops only scale **size**, never retune primary side rules on holdout data (ANTI_OVERFIT.md).

## Finds applied

- WINNER v23_devin_overlay (vol-z overlay, macro block)
- v20b XLP/SPY defensive stand-aside
- Options playbook: debit spreads, react cut −30%, trail big moves
- Feedback size mult after win streak (not theoretical full-cash ledger)
- Failure protocol: do not stack vanity WR filters

## Finds avoided

- Raw price XGB as primary (`poc_va_xgb` any_edge=false)
- Full Coulling stack over-filter (v17)
- 90% WR sniper as whole book (thin n)
- v24 risk_pct≈1.0 full-account options (DD catastrophe)
- Feedback ledger that ignores capital tied in open options

## Pass bar target

Equity path: PF ≥ 1.2, |DD| ≤ 25%, Sharpe ≥ 0.5, trades ≥ 40 on claimed window.  
Options path: paper/react rules first; do not promote options WINNER without OOS defined-risk evidence.

## Kill criteria

If equity sleeve underperforms v23 on same window by Sharpe & PF with worse DD → fail and re-research.  
If attack mode blows through flatten DD in sim → lower attack_risk_pct, do not disable cut rules.
