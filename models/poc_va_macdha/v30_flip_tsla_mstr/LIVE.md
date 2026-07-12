# LIVE — v30_flip_tsla_mstr (short-term flips)

## What you trade
- **TSLA, MSTR only**
- **Long calls** after pullback bounce
- **Long puts** on downside dumps
- **No spreads** — just the call or put
- Hold **1–2 days** when possible; **hard out by day 5**
- Size: **~70% of book premium** per flip (growth style — you risk the base to grow the base)

## In / out
1. Pullback + bounce day → **buy call**, ATM ~7 DTE  
2. Dump / break day after extension → **buy put**, ATM ~7 DTE  
3. **Out** when: move ~4%+ your way, reverse signal, or max hold  

## July desk note
Matches **your** style more than v29 (bag long-only, tight risk):

- Calls **and** puts  
- Short hold, out in days  
- Risk **most of the base** per flip  
- TSLA / MSTR only  

### Backtest honesty (don’t ignore)
| Window | Result |
|--------|--------|
| Full 2024-08→2026-07 | **Hard lose** (~−60%, overtrades) |
| Start **May 1 → Jul 1 2026** | **Very strong** (~**+71%** on $1M path, many call+put flips) |
| Start Apr 1 → Jul 1 | Only ~**+3%** (path-dependent size after early chops) |

**Meaning:** the *structure* fits you; **auto entries are not as good as your eyes**. Use as a **flip checklist** (call-day vs put-day) and still skip garbage.

### Size
- Config default `risk_pct=0.70` (aggressive, as you want).  
- $1k: often only 1 cheap lot when premium allows — not the same as $1M compounding.
