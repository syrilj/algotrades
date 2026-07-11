# poc_va_macdha — Model Registry

**Shared improve module:** `models/_shared/PLAYBOOK.md`  
**Findings log:** `models/_shared/findings.jsonl` · CLI: `.venv/bin/python tools/findings.py`  
If a research finding fails OOS → `models/_shared/FAILURE_PROTOCOL.md` (re-research; do not stack filters).

| Version | Path | Notes |
|---------|------|-------|
| **v1_2h4h** | `models/poc_va_macdha/v1_2h4h/` | Frozen: POC/VA + 2H signals + 4H St.MACD-HA |
| **v2_vwap** | `models/poc_va_macdha/v2_vwap/` | Active: + swing-anchored VWAP + volume expand |
| **v13_long_oos** | `models/poc_va_macdha/v13_long_oos/` | Phase A frozen v13 on 2020–2026 **1D** (Yahoo 1H 730d cap). **FAIL** bar: PF 1.24 ✓, DD −36% ✗, Sharpe 0.45 ✗. See `OOS_REPORT.md`. |
| **v17b_book_vpa_light** | `models/poc_va_macdha/v17b_book_vpa_light/` | Book-derived Coulling light gates on v15 meta. PASS bar; PF 2.88 (>v15), DD −9.6% better; Sharpe 1.82 < v15. Full stack v17 FAIL vs winner (over-filter). See BOOK_INSIGHTS.md. |
| **v18_wr90** | `models/poc_va_macdha/v18_wr90/` | High-WR sniper sleeve (APLD+IONQ). Stable **83.3% WR**, Sharpe 1.39, PF 19.7, n=12. **90% target not robust** (sample_noise). Satellite beside v15, not WINNER. |
| **v20b_macro_light** | `models/poc_va_macdha/v20b_macro_light/` | **WINNER** risk-adj book: v16 meta+Kelly + XLP/SPY defensive block + drop ARM. Sharpe **2.23**, PF **3.04**, DD **−10%**, ret +114%. See BOOK_RECIPE.md. |
| **v19_node_cloud** | `models/poc_va_macdha/v19_node_cloud/` | Explore: **react not predict** — VAL/POC/VAH nodes + EMA cloud compass; target = nearest upside node. Live GEX walls: `poc_va_gex/v1_node_cloud`. |
| Active run | `runs/poc_va_macdha/code/signal_engine.py` | What backtest loads |
| Pine v1 | `pine/poc_va_macdha_v1.pine` | TradingView overlay |
| Pine v2 | `pine/poc_va_macdha_v2_vwap.pine` | TradingView + VWAP |

## How to iterate

1. Read findings: `.venv/bin/python tools/findings.py working` / `failed` / `next`
2. Copy WINNER engine → `models/poc_va_macdha/vN_name/` + `HYPOTHESIS.md` from `models/_shared/templates/`
3. Edit `MODEL_SPEC` + toggles; sync Pine under `pine/`
4. Backtest: `python3 -c "from pathlib import Path; from backtest.runner import main; main(Path('runs/poc_va_macdha').resolve())"`
5. Record: `.venv/bin/python tools/findings.py record --family poc_va_macdha --version vN_name --status auto --kind <kind> --summary "..." --metrics-json models/poc_va_macdha/vN_name/results.json`

## Suggested next improvements

1. **Confidence sizing** — score = mean(HA, above_VWAP, vol_expand, POC_hold); signal ∈ {0.25,0.5,1.0}
2. **Per-symbol configs** — MU strong on 2H/4H; SPY better daily; APLD needs stricter vol/VWAP
3. **Adaptive APT on** (`use_adapt_apt=True`) in high-vol names (IONQ/TSLA)
4. **Shorts** — mirror rules when `dir<0`, below VWAP, HA red, near VAH
5. **True session VP** — minute RTH bars when available (Yahoo 1h is a compromise)
6. **Risk** — ATR stop under VAL / swing VWAP; max DD kill-switch
7. **Validation** — walk-forward by quarter; don’t retune on full sample
8. **Shared findings** — after every version, `tools/findings.py record` (fail → FAILURE_PROTOCOL / re-research)

## Training sweep (2026-07-11)

15 variants trained on TSLA/ARM/MU/SPY/IONQ/APLD, 1H→features (or 4H), window 2024-08-01..2026-07-11.

**Winner by avg win rate:** `v8_4h_daily` (~58.5% avg WR, port WR 59.4%, Sharpe 0.77)

Rules: 4H bars, daily St.MACD-HA green, close≥swing VWAP, LazyBear squeeze mom>0, block price↑+volume↓ red-flag, exit below VWAP.

Artifacts: `WINNER.json`, `TRAINING_LEADERBOARD.json`, `pine/poc_va_macdha_v8_4h_daily_WINNER.pine`


## v12 Regime Router (current winner)

Per-symbol specialization from the training sweep:

| Symbol | Bucket | Variant |
|--------|--------|---------|
| TSLA | high_beta | v11_sqz_vol_block |
| ARM | high_beta | v8_4h_daily |
| IONQ | high_beta | v8_4h_daily |
| APLD | high_beta | v5c_confirm_vwap |
| MU | traditional | v4b_block_only |
| SPY | traditional | v10_tight |

- High-beta: squeeze/VWAP/vol-confirm stacks
- Traditional (MU/SPY): simpler red-flag block or tight filters
- Live portfolio: WR ~62.7%, Sharpe ~1.66 (see `v12_regime_router/results.json`)
- Routing map: `models/poc_va_macdha/ROUTING.json`

## v15_meta_xgb (Phase B)
Shipped under `models/poc_va_macdha/v15_meta_xgb/` with modest half-year OOS lift (+2.4pp hit, +0.74pp exp). **Not promoted to WINNER** pending portfolio PF/Sharpe/DD vs v13; see `v15_meta_xgb/MODEL.md`.
