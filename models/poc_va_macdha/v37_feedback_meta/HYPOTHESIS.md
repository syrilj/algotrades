# v37_feedback_meta

**Parent:** `v23_devin_overlay` (current WINNER)  
**Goal:** Beat v23 / v20b / v15 on portfolio Sharpe + PF + DD + return by applying *only* feedback-validated soft improvements — no new hard entry gates.

## What we keep (working findings)
- Primary side = specialist rules (v13 routing / v20b DNA)
- Meta-XGB secondary on engine-exit labels
- XLP/SPY defensive macro block; drop ARM
- Volume-z soft conviction boost
- Soft structure sizing (v32 lesson: hard filters kill)

## What we change (new AFML + evolve feedback)
1. **Continuous meta size** instead of thr=0.6 step map `{0.25,0.5,1.0}`  
   Soft skip ~0.52 + half-Kelly blend to [0.25, 1.0]
2. **Soft feature mults** from v36 evolve (atr_pct, room_pct, macd_hist, ret_5d) — never hard-block
3. **Soft structure/chase** mults (good ×1.12, chase ×0.55)
4. Light sector/QQQ RS boost to meta probability

## Explicitly not doing
- Hard vol/EMA200 entry gates (v15_structure / v29/v30 fail)
- Predicting next close as primary
- Options track as equity claim

## Promote if
OOS / same-window portfolio beats v23 on utility: higher return **or** better Sharpe at similar DD, with PASS_BAR (PF≥1.2, |DD|≤25%, Sharpe≥0.5, n≥40).
