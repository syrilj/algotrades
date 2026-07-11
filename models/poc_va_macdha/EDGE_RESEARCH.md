# Edge Research Brief — How to Improve Models (poc_va_macdha)

**Date:** 2026-07-11  
**Goal:** Find the best path to a durable edge — not vanity win rate.  
**Sources:** Local runs + [LSE ML Studio / Education](https://londonstrategicedge.com/machine-learning-studio/) + SSRN / AFML literature.

**Durable log:** findings from this brief are recorded in `models/_shared/findings.jsonl`.  
Future versions must follow `models/_shared/PLAYBOOK.md`. Failures → `FAILURE_PROTOCOL.md` + `tools/findings.py next`.

---

## Verdict (read this first)

Your edge so far is **rule specialization + risk**, not price-predicting ML.

| Layer | Status | Evidence |
|-------|--------|----------|
| Primary rules (POC/VA + HTF MACD-HA + filters) | Working as signal generator | Specialists + router beat one-size-fits-all |
| Per-symbol specialists (v13) | Best selection so far | ~64% avg WR, PF ~1.45, Sharpe ~1.08 (short window) |
| Risk / Kelly (v14) | Improves DD path | DD −24% vs worse DD on earlier stacks; still lags buy&hold excess |
| Naïve XGB filter (`poc_va_xgb`) | **No edge** | `any_edge: false` — filter did not lift hit rate or expectancy |

**Best development path:** keep rules as **primary side**, rebuild ML as **true meta-labeling** (filter + size) on **actual trade outcomes**, with **longer history + purged / combinatorial CV**. Do not train XGB/LSTM to predict next close from bars alone.

---

## What you have today

### Architecture (correct direction)

```
OHLCV → Volume profile (POC/VAL/VAH) + HTF St.MACD HA
      → Rule candidate (side = long)
      → Filters (VWAP / vol / red-flag / squeeze)  [manual meta-rules]
      → Optional risk/Kelly sizing (v14)
```

This already matches the industry pattern called **meta-labeling** (Lopez de Prado / Joubert SSRN): primary model chooses *side*; secondary model chooses *whether / how much*. Your secondary layer is still mostly hand-tuned flags, not a trained probability model.

### What already worked (from FEATURE_INSIGHTS + WINNER)

- **High-beta** (TSLA, IONQ, APLD, ARM): `block_red_flag` lifts WR a lot (+8–14pp); VWAP / vol-confirm help; 4H often better for ARM/IONQ.
- **MU:** simple red-flag block; avoid squeeze-mom stacks.
- **SPY:** VWAP trend / above VWAP; **avoid** `block_red_flag` and `vol_confirm` (negative lift).

That heterogeneity is the real edge signal: **one global filter set destroys portfolio edge**.

### What failed

`runs/poc_va_xgb/train_xgb_walkforward.py` + `runs/artifacts/xgb_report.json`:

- Label = fixed **5-bar forward return > cost** (not your strategy’s exit / PnL).
- Candidates ≠ your live specialist engines.
- Threshold 0.55 often took **all** test trades → zero lift.
- Result: **no OOS edge**.

So ML didn’t fail conceptually — the **label and candidate definition** failed.

### Honest portfolio constraints

- Window still ~2024-08 → 2026-07 for most specialist work (~2y).
- Excess vs buy&hold often **negative** (bull tape); edge must be measured as **risk-adjusted / regime-conditional**, not “beat SPY in a melt-up.”
- APLD/IONQ high WR with low trade counts → easy to overfit specialists.

---

## What LSE teaches (curriculum map → your stack)

LSE pages are SPA-rendered; usable signals from sitemap + meta + FAQ:

| LSE topic | URL theme | Apply here |
|-----------|-----------|------------|
| ML Studio | Train XGB / RF / CatBoost / LSTM on their data | Use as **GPU sandbox** later; don’t replace local research loop yet |
| Model evaluation | Walk-forward, precision-recall, ROC | Promote by **OOS expectancy + PF + DD**, not train WR |
| Feature engineering | Core concept pages | Features from **engine state at entry**, not raw close |
| Walk-forward | `/machine-learning/time-series/walk-forward/` | Keep WF; upgrade to purged / CPCV when sample allows |
| XGBoost | Tabular alpha, depth/lr/reg, feature importance | Secondary filter only; shallow trees |
| Position sizing / drawdown | Risk-management section | Keep v14 path; map `P(win)` → Kelly fraction |
| Tick archive (133B ticks) | Free Parquet/CSV | Better **true session VP** than Yahoo 1H compromise |
| Brue + lse-data (GitHub) | Strategy language + data client | Optional later for live/tick parity |

LSE product claim (Company/FAQ): tick backtests, ML studio calling models inline, free datasets. **Use LSE for data depth and education; keep your research code as source of truth.**

---

## What SSRN / AFML says (papers that map to this repo)

1. **Meta-labeling** — Joubert, *Meta-Labeling: Theory and Framework* ([SSRN 4032018](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4032018)): secondary ML filters false positives and sizes; primary keeps high recall.  
2. **AFML (Lopez de Prado)** — triple-barrier labels, event sampling, meta-labels = “was the primary trade profitable under barriers?”  
3. **Hudson & Thames / mlfinlab replications** — primary trend/MR + RF meta-label improved efficacy when labels are event-based.  
4. **CPCV vs walk-forward** — Arian et al. ([SSRN 4686376](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4686376)): combinatorial purged CV has lower probability of backtest overfitting than naïve walk-forward alone.

### Labeling you should switch to

For each **rule-generated entry** at `t`:

- Barriers: profit take / stop / max hold (aligned with your exits: HTF red, below VWAP, etc.).
- `y_meta = 1` if trade PnL after costs > 0 (or > buffer).
- Features = state at entry: dist_POC/VAL/VWAP in ATR, HA age, vol expand, red-flag, symbol/regime, optional SPY trend.
- Model outputs `P(success)` → gate (`>= thr`) and size (`0.25/0.5/1.0` or fractional Kelly).

That is the LSE XGBoost path **done correctly**, and the reason your first XGB run found nothing.

---

## Recommended development sequence (best edge path)

### Phase A — Prove the primary has OOS flesh (1–2 days CC)

1. Freeze **v13 specialists + routing** as primary.
2. Re-backtest with `start_date` **2018 or 2020**, liquid universe (SPY/QQQ/AAPL/NVDA/META + MU; isolate IONQ/APLD).
3. Walk-forward by **quarter**; never retune on test.
4. Pass bar: OOS PF > 1.2, max DD < 25%, Sharpe > 0.5 (same as `IMPROVE_ML_BACKTEST.md`).

If Phase A fails → edge is sample noise; stop adding ML.

### Phase B — True meta-labeler (core ML edge)

1. Candidate logger from real `signal_engine` entries (not synthetic HA∧VWAP∧POC).
2. Triple-barrier / trade-outcome labels.
3. Walk-forward XGB (lr 0.01–0.05, depth 3–5, L1/L2) + SHAP/gain prune.
4. Embargo/purge overlapping labels; when N is large enough, CPCV for PBO.
5. Ship as `v15_meta_xgb`: primary side unchanged; secondary gate + size.

### Phase C — Data upgrade (edge quality)

1. Prefer LSE tick/Parquet (or RTH minute) for **true volume profile**.
2. Regime feature: SPY HTF green / vol regime as shared feature for specialists.
3. Keep per-symbol models or a single model with symbol + regime embeddings — do **not** force one filter set.

### Phase D — Explicitly defer (oceans)

- LSTM/transformers predicting price (LSE studio has them; low ROI vs meta-label for this strategy).
- RL position agents before meta-label works.
- Replacing POC/VA primary with black-box side prediction.

---

## Metrics that define “edge” here

Promote a version only if **all** improve OOS vs frozen baseline:

1. Expectancy after costs  
2. Profit factor  
3. Max drawdown  
4. Deflated / OOS Sharpe (or at least WF Sharpe)  
5. Trade count still large enough (avoid 10-trade miracles)

Win rate alone is a vanity metric (`IMPROVE_ML_BACKTEST.md` already says this).

---

## Decision audit (research)

| Decision | Choice | Why |
|----------|--------|-----|
| Primary architecture | Keep rules | Specialists already encode edge; XGB side failed |
| ML role | Meta-label filter/size | AFML + Joubert + LSE eval guidance |
| Next build | v15 meta-XGB on real candidates | Fixes failed XGB experiment |
| Data | Longer history + better VP | Current 2y window underpowered |
| Deep learning | Defer | Completeness without boiling the ocean |

---

## References

- Local: `IMPROVE_ML_BACKTEST.md`, `MODEL.md`, `WINNER.json`, `FEATURE_INSIGHTS.json`, `runs/artifacts/xgb_report.json`
- LSE: https://londonstrategicedge.com/machine-learning-studio/ · education hub · walk-forward · XGBoost · model evaluation · risk/sizing
- SSRN: 4032018 (meta-labeling), 4686376 (CPCV / overfitting)
- GitHub: `londonstrategicedge/lse-data`, `londonstrategicedge/brue`
