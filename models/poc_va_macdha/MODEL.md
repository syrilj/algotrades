# poc_va_macdha — Model Registry

**Shared improve module:** `models/_shared/PLAYBOOK.md`  
**Findings log:** `models/_shared/findings.jsonl` · CLI: `.venv/bin/python tools/findings.py`  
If a research finding fails OOS → `models/_shared/FAILURE_PROTOCOL.md` (re-research; do not stack filters).

| Version | Path | Notes |
|---------|------|-------|
| **v35_softstruct_bag8** | `models/poc_va_macdha/v35_softstruct_bag8/` | **OPTIONS DEFAULT (2026-07-11 loops r2)**: v29 shell + v32 soft-structure size overlay + bag8 (+COIN+RKLB). Mean OOS **0.1458** (v34 0.1018, v29 0.0282), 4/5 folds vs both; full **+73%**, DD −9.1%, Sharpe **1.78**, WR 86%. Interaction: bag8 w/o overlay FAILS. Caveat: lost wf_fold3 2026H1 to v34 (fallback). See `LIVE.md`. |
| **v34_bag6_opts** | `models/poc_va_macdha/v34_bag6_opts/` | **OPTIONS DEFAULT by pure-OOS rule (2026-07-11 loops)**: v29 engine + bag +TSLA+GME. Mean OOS score **0.1018** vs v29 0.0282 (3 wins+2 ties/5 folds); full +66%, DD −7.8%, Sharpe 1.59, WR 85%. Growth sleeve: bag6+soft_strong blends 4/5 folds, +80–100%. Kills: v32 standalone OOS-fail; risk 15–20%/vol_z/Kelly sizing OOS-fail. See `LIVE.md`. |
| **v36_sharpe_meta** | `models/poc_va_macdha/v36_sharpe_meta/` | **$1k live recipe (2026-07-12)**. Multi-model Sharpe reward + feature mine + MLP soft-size. Primary equity **v15_meta_xgb** (sh 1.95, +102% on 1k bag). Options sleeve **v31** (sh 1.45, +53%). See `LIVE_RECIPE.json` + `runs/poc_va_feature_evolve_1k/`. |
| **v32_soft_react_opts** | `models/poc_va_macdha/v32_soft_react_opts/` | **OPTIONS research winner (soft structure size)**. Size ×1.15 at node+cloud+room, ×0.55 weak; no hard blocks. Full-window +108% Sharpe **1.49**; WF **3/3** vs v28. See `results.json`. |
| **v31_selective_nodes_opts** | `models/poc_va_macdha/v31_selective_nodes_opts/` | Hard node gates underperformed v28 (+87%). Prefer v32 soft sizing. |
| **v28_feedback_opts** | `models/poc_va_macdha/v28_feedback_opts/` | **OPTIONS prior baseline**. +104.1%, DD −11.2%, Sharpe 1.40. Parent of v32. |
| **v29_feedback_loop** | `models/poc_va_macdha/v29_feedback_loop/` | **FAIL** hard volume/EMA stack: +4.9%, Sharpe 0.45. Do not ship. |
| **v30_feedback_pro** | `models/poc_va_macdha/v30_feedback_pro/` | **Blocked** — same hard-filter pattern as v29; rewrite as soft/selective only. |
| **v26_opts_evolve** | `models/poc_va_macdha/v26_opts_evolve/` | v22 DNA + **14 DTE**. +64.5% ret, DD −9.3%, Sharpe 1.40. Best risk-adj options baseline. |
| **v22_opts_live** | `models/poc_va_macdha/v22_opts_live/` | Hunt-evolved options bag IONQ/AVGO/HOOD/MU, ~21 DTE, +59.8%, WR 82%. Parent of v26. |
| **v25_regime_grow** | `models/poc_va_macdha/v25_regime_grow/` | Equity hedge sleeve (weaker than v22/v26 for growth). Live risk UI still useful. |
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

## Live risk (v25)

```bash
python3 tools/risk_manager.py plan --symbol APLD --account 1000 --conf 0.85 --vol-z 1.8 --qqq-ok
python3 tools/trade_desk.py risk APLD --account 1000 --conf 0.85 --vol-z 1.8
# full human checklist:
open models/poc_va_macdha/v25_regime_grow/RISK_PLAYBOOK.md
```

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
