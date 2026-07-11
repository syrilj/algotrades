# Performance & Model Routing

Source of truth: `WINNER.json`, engine `results.json`, `TRAINING_LEADERBOARD.json`, `tools/model_registry.py`.  
No invented metrics — numbers below are from those files (window ~2024-08..2026-07 where noted).

## Overall engine ranking (portfolio score)

`recommend_model()` / `rank_models(engines_only=True)` — composite favors WR + Sharpe + PF − DD penalty.

| Rank | Model | Sharpe | PF | Max DD | Calmar | WR | Trades | Total ret |
|------|-------|--------|-----|--------|--------|-----|--------|-----------|
| 1 | **v15_meta_xgb** (DEFAULT / WINNER) | 2.128 | 2.677 | −13.2% | 4.12 | 62.3% | 130 | +130.5% |
| 2 | v16_meta_risk | 2.062 | 2.442 | −10.8% | 4.61 | 58.6% | 133 | +116.5% |
| 3 | v15_regime_specialists | 1.779 | 3.635 | −17.5% | — | 63.9% | 83 | — |
| 4 | v17b_book_vpa_light | 1.815 | 2.879 | −9.6% | — | 60.2% | 98 | — |
| 6 | v14_risk_kelly | 1.722 | 1.789 | −24.0% | 3.88 | 61.1% | 221 | +252.4% |
| 7 | v12_regime_router | 1.661 | 1.645 | −39.0% | 2.82 | 62.7% | 201 | +315.3% |

**v15 vs v14 (`v15_meta_xgb/results.json` → `vs_v14`):** Sharpe +0.41, PF +0.89, DD better by ~10.7pp, WR +1.2pp.  
v14 wins **raw return / trade count**, loses **risk-adjusted** (Sharpe/PF/DD). Do **not** revert DEFAULT to v14.

Training-sweep (no claim as live default): highest leaderboard Sharpe is `v4_voldiv` (0.98) — research variant, not the promoted engine.

## Per-symbol winners (`--model auto`)

From `rank_models_for_symbol` over engines with per-symbol rows (v15/v14 folders often lack `per_symbol`; routing uses specialists / v12 / leaderboard engines):

| Symbol | Best hist engine | Sharpe | WR | Trades | Notes |
|--------|------------------|--------|-----|--------|-------|
| TSLA | v13_specialists | 0.75 | 58.5% | 41 | Prefer auto |
| MU | v1_2h4h | 1.51 | 51.3% | 39 | Then v12 |
| APLD | v12_regime_router | 1.54 | 75.0% | 28 | Strong specialist |
| ARM | v12_regime_router | 0.52 | 53.3% | 30 | Ties near v8_4h |
| IONQ | v8_4h_daily | 1.55 | 74.2% | 31 | 4H stack |
| SPY | v13_specialists | 0.74 | 51.4% | 37 | Avoid over-filtering |
| NVDA (no hist row) | falls back to **v15_meta_xgb** | 2.13 port | — | — | Overall default |

## Recommendation

- **Default live engine:** `v15_meta_xgb` (`DEFAULT_MODEL`). Matches `WINNER.json` + PASS_BAR.
- **Use `--model auto` when:** scanning a named sleeve (TSLA/MU/APLD/ARM/IONQ/SPY) where hist score differs from v15; rotate/picks over mixed names.
- **Stay on fixed v15 when:** watch refresh speed matters and you want one engine; or symbol has no per-symbol hist (e.g. NVDA).
- **Do not use WR alone** for promotion — PASS_BAR requires PF ≥ 1.2, |DD| ≤ 25%, Sharpe ≥ 0.5, ≥ 40 trades.

## Trade-desk speed (what was slow / what changed)

| Path | Bottleneck | Fix |
|------|------------|-----|
| `scan_picks` / `rotate` | `analyze(..., ranks=True)` rebuilt full symbol ranks every name | `ranks=False` in scan; `best_hist` via `recommend_model` |
| `_compute_state` | `rank_models_for_symbol` per bar path | `hist_win_rate()` on cached cards |
| `all_model_cards` | Re-read JSON every call | mtime-keyed process cache |
| `rank_sector_flows` | Serial yfinance per ETF | One batched `_download_close([SPY]+ETFs)` |
| `watch` | Already `ranks=False` | Engine module cache in `_load_engine` |
| Remaining | Per-symbol `yf.download` in analyze/watch | Dominant cost; batch multi-ticker fetch is next if needed |

## Structure-gate backtest probe (volume + EMA22 + EMA200)

**Hypothesis:** Hard-filtering v15 entries with volume awake + above EMA200 (+ optional EMA22 soft path) improves Sharpe/PF/DD/Calmar.

### A/B results (same window/codes as `runs/poc_va_v15`)

| Variant | Sharpe | PF | Max DD | Calmar | WR | Trades | Total ret | Verdict |
|---------|--------|-----|--------|--------|-----|--------|-----------|---------|
| **Baseline v15** | **2.128** | 2.677 | −13.2% | **4.12** | 62.3% | 130 | **+130.5%** | WINNER |
| Full structure (`poc_va_v15_structure_gates`) | 1.747 | **2.799** | **−11.5%** | 3.23 | **63.6%** | 88 | +83.0% | **FAIL** |
| Light EMA200+red_flag (`poc_va_v15_struct_light`) | 1.857 | 2.623 | −13.2% | 3.19 | 61.6% | 99 | +96.5% | **FAIL** |

**Conclusion:** Hard structure gates **do not** clear PASS_BAR promotion vs v15 (need Sharpe **and** risk-adj improvement). Slightly better PF/DD/WR is vanity if Sharpe/Calmar/return fall.  
**Live policy:** keep volume / 22 EMA / 200 EMA as **advisory** labels in `trade_desk` (BREAKOUT WATCH, AVOID structure broken). Do **not** bake hard gates into the default engine yet.

Artifact: `models/poc_va_macdha/STRUCTURE_GATES_AB.json`.

### Commands used

```bash
.venv/bin/python3 -m backtest.runner runs/poc_va_v15_structure_gates
.venv/bin/python3 -m backtest.runner runs/poc_va_v15_struct_light
```

## Related files

- `models/poc_va_macdha/WINNER.json`
- `models/poc_va_macdha/v15_meta_xgb/results.json`, `v14_risk_kelly/results.json`
- `models/poc_va_macdha/STRUCTURE_GATES_AB.json`
- `tools/model_registry.py`, `tools/trade_desk.py`
- `models/_shared/PASS_BAR.json`
