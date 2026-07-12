# v37_feedback_meta (WINNER)

**Parent:** `v23_devin_overlay`  
**Status:** Promoted — beats v23 / v20b / v15 on 2024-08..2026-07 1H head-to-head.

## Recipe
1. **Primary side** — same specialist routing as v23 (POC/VA + HTF MACD-HA + XLP macro + ARM drop)
2. **Meta-XGB** — same booster as v23 (engine-exit labels)
3. **Continuous soft size** — skip ~0.52, ramp to full ~0.70, half-Kelly blend (no thr=0.6 step map)
4. **Soft feature mults** (evolve feedback, never hard-block):
   - `atr_pct` high → cut
   - `room_pct` open → boost; tight → cut
   - `macd_hist` / `ret_5d` extremes → soft chase cut
   - structure good ×1.12; chase ×0.55
5. **vol_z + light sector/QQQ RS** proba boost (soft)

## Results (1H, $1M, commission 0.1%)

| Model | Return | Sharpe | Max DD | PF | n | WR |
|-------|--------|--------|--------|-----|---|-----|
| **v37_feedback_meta** | **+202%** | **2.52** | -13.5% | 3.41 | 131 | 68% |
| v23_devin_overlay | +130% | 2.21 | **-9.1%** | **3.54** | 92 | 65% |
| v20b_macro_light | +114% | 2.23 | -10.0% | 3.04 | 101 | 64% |
| v15_meta_xgb | +49% | 1.14 | -21.0% | 1.74 | 52 | 44% |

## Tradeoffs
- Higher return & Sharpe, more trades — pays with deeper max DD vs v23
- If you need the calmest equity path, keep `v23_devin_overlay` as DD sleeve
- Meta booster is still full-sample; purged WF stitch is the next honesty upgrade

## Live
Use `signal_engine.py` + `meta_xgb_final.json` in this folder (same layout as v23).
