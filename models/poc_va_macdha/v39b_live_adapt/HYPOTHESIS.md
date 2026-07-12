# Hypothesis

**Version:** `v39b_live_adapt`  
**Family:** `poc_va_macdha`  
**Parents:** `v39_vpa_score` (fail promote) + `v38_research_stack` (WINNER)  
**Date:** 2026-07-12

## Claim

Keep the **react-not-predict** stack (nodes + Coulling VPA + EMA path), but retune for **live trading that adapts bar-to-bar**:

1. **Ablation A/B/C from v39 fail** — no stand-aside floor, mild EMA bear (×0.90), halved negative VPA weights → recover capacity vs WINNER bag  
2. **Faster sensors** — VPA look 3 / vol SMA 14 / stop look 5 (vs 5/20/8) so effort flips show up in 1–3 hours  
3. **Rapid adapt** — `vpa_mom` (score vs 8-bar mean), `vol_regime` (recent |vol_z|), stacked streak with mean-reversion, mid-trade size shrink when volume narrative breaks  
4. **Live API** — `record_trade(pnl)` + `live_adapt_snapshot()` so the desk updates size after each fill without waiting for a full retrain  

Primary SIDE still frozen. Secondary only.

## Pass bar

Same WINNER bag 1H vs `v38`:

- Promote if Sharpe ≥ v38 − 0.05 **and** ret ≥ 0.90 × v38 (capacity recovered)  
- Soft win if DD better and Sharpe ≥ 2.4 with n ≥ 100  
- Kill if ret collapses again like v39 (+224% vs +310%) without DD edge worth it  

## Live use

```bash
.venv/bin/python tools/trade_desk.py IONQ --model v39b_live_adapt
# after each trade outcome in a notebook / desk loop:
# eng.record_trade(pnl=+120, symbol="IONQ")
# eng.live_adapt_snapshot()
```
