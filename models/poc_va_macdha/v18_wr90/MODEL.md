# v18_wr90 — High win-rate sniper sleeve

**Target:** WR ≥ 90%  
**Achieved (stable):** WR **83.3%** · Sharpe **1.39** · PF **19.7** · DD **−11.3%** · **n=12**

## What it is
Satellite sleeve (not full-book WINNER). Universe locked to **APLD + IONQ** with:
- QQQ trend regime
- Volume expand
- Block red-flag (Coulling weak rally)

Built from book findings + v16_wr80 path + feedback loop.

## 90% verdict
**Not robust on this window.** Extra filters (`vol_z`, commitment, EMA200, meta thr≥0.75) either:
- stay ~83%, or
- spike to 100% on **n=2–4** trades that **don’t reproduce**

Full-book meta sniper (thr=0.70) peaks at **WR 68.8%** then goes to 0 trades.

## Use how
- Run **beside** `v15_meta_xgb` (capacity/Sharpe king), not instead of it
- Treat as high-precision small-cap sleeve
- Do not claim 90% until longer OOS / more names / paper live

## Paths
- Engine: `signal_engine.py`
- Results: `results.json`
- Loop: `ENGINE_LOOP.json`
- Run: `runs/poc_va_wr90/`
