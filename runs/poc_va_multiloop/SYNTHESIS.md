# Parallel feedback loops — synthesis

**Date:** 2026-07-11  
**Runner:** `runs/poc_va_multiloop/run_parallel_loops.py`  
**Input:** `runs/poc_va_wr80/artifacts/enriched_trades.csv` (v14-path book, n=221)

## Loops run

| Loop | Objective | Universe | Best stack | n | WR | OOS WR | OOS exp |
|------|-----------|----------|------------|---|----|--------|---------|
| A sniper greedy | WR | APLD+IONQ | `f_tech_stack` | 16 | 75% | 71% | +1.8 |
| B large greedy | Expectancy | TSLA+MU | `f_qqq_and_mag7` → `f_not_red_flag` | 16 | 81% | 71% | **+4.9** |
| C broad greedy | Balanced | All | `f_not_red_flag` → drop ARM → `f_qqq_trend` | 29 | 83% | **83%** | +5.7 |
| D large forced | Mag7 path | TSLA+MU | qqq→mag7→red→vol→macd | 13 | 77% | — | +3.0 |

## Combo search winners

**Sniper (n≥10):** `f_qqq_trend + f_local_macd_green` → train/test WR **100%/100%**, n=11. Thin but clean — basis for v18 sniper harden.

**Large (n≥12):** `f_qqq_trend + f_vol_expand + f_above_sma20` → OOS WR 80%, OOS exp +6.2 (n=12). Alternate: Mag7∧not-red stacks ~n=15, train WR 89%, test WR 67%, strong OOS exp.

## Models created (not promoted)

- `models/poc_va_macdha/v18_dual_sleeve/` — sniper + large in one engine
- `models/poc_va_macdha/v18_largecap_regime/` — TSLA/MU Mag7 sleeve alone

**WINNER unchanged:** `v15_meta_xgb` (PASS_BAR min_trades=40; sniper-alone still fails that gate).

## Next research steps

1. Engine backtest v18_dual_sleeve with Mag7 OHLCV in data_map.
2. Compare sleeve metrics vs v15 / v16 on same window.
3. Only promote if PF≥1.2, |DD|≤25%, Sharpe≥0.5, trades≥40, OOS expectancy>0.
4. Keep LSE GEX as future meta on large sleeve (journal first).
5. Run `runs/poc_va_antioverfit/stress_holdout_ranges.py` on any new filter stack before promote.

## Local Mag7 engine proxy (2026-07-11 follow-up)

Runner: `runs/poc_va_multiloop/engine_backtest_v18_proxy.py`  
Artifact: `runs/poc_va_multiloop/artifacts/V18_ENGINE_PROXY.json`

- Cached Mag7+universe OHLCV → v18 `SignalEngine.generate` → close-to-close trades.
- **53 trades**, proxy PF strong, chronological test WR **~77%** (train ~55%) — holdout does **not** look like “only good on known data.”
- PASS_BAR trade/PF/expectancy gates clear on proxy; **equity DD / official Sharpe still not evaluated** → **do not promote yet**.
- WINNER remains `v15_meta_xgb` until official run harness confirms DD/Sharpe.
