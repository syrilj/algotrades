# Book Research & Model Findings

**Date:** 2026-07-11  
**Scope:** Insights from `books/`, backtests into `poc_va_macdha` / `poc_va_gex`, and durable log entries in `models/_shared/findings.jsonl`.

---

## 1. Books reviewed

| # | File | Focus |
|---|------|--------|
| 1 | `Anna Coulling A Complete Guide To Volume Price Analysis` | Wyckoff / VPA: effort vs result, no demand, stopping & topping volume, climax |
| 2 | `george_soros_the_alchemy_of_finance_english.pdf` | Reflexivity: self-reinforcing then self-defeating boom/bust |
| 3 | `Thinking-strategically-the-competitive-edge-in-business-politics.pdf` | Game theory: credible commitment before acting |
| 4 | `options-strategies-quick-guide.pdf` | Strategy choice by outlook / IV; climax ≈ high-vol regime |

Extracts (keyword samples): `books/_extract/`

---

## 2. Book ideas → quant gates

| Book idea | Signal / rule | Model gate |
|-----------|---------------|------------|
| Effort vs result (Wyckoff/Coulling) | Wide spread + thin volume = anomaly | `require_effort_ok` |
| No demand | Up bar + low volume | `block_no_demand` (+ `block_red_flag`) |
| Stopping volume | After decline: high vol + narrow spread | `stopping_volume` → `allow_stopping_reclaim` |
| Topping / buying climax | Extreme volume into a rally | `block_topping_volume`, `block_buying_climax` |
| Reflexivity (Soros) | Sustained confirm, then climax fails | Prefer `reflexive_up`; avoid climax chase |
| Credible commitment (Dixit/Nalebuff) | Act only with volume confirmation | `require_commitment` = confirm ∪ stopping_reclaim ∪ reflexive |
| Options / high-vol regime | Climax ≈ realized-vol spike | Size cut / stand aside — not a new side model |

Mapping doc: `models/poc_va_macdha/v17_book_vpa/BOOK_INSIGHTS.md`

---

## 3. Backtest results (same window)

**Window:** 2024-08-01 → 2026-07-11 · **Interval:** 1H · **Pass bar:** PF ≥ 1.2, |DD| ≤ 25%, Sharpe ≥ 0.5, trades ≥ 40

| Version | WR | Sharpe | PF | Max DD | Trades | vs `v15` winner | Verdict |
|---------|----|--------|-----|--------|--------|-----------------|---------|
| **v15_meta_xgb** (WINNER) | 62.3% | **2.13** | 2.68 | −13.2% | 130 | — | Keep WINNER |
| **v17_book_vpa** (full stack) | 59.3% | 1.62 | 2.63 | −9.4% | 91 | Worse Sharpe/return | FAIL vs winner (over-filter) |
| **v17b_book_vpa_light** | 60.2% | 1.82 | **2.88** | **−9.6%** | 98 | Better PF/DD; worse Sharpe/return | PASS bar; quality↑ capacity↓ |
| **v18_wr90** (sniper sleeve) | **83.3%** | 1.39 | **19.7** | −11.3% | 12 | High WR, thin n | Stable high-WR sleeve; **90% not robust** |
| v16_wr80 (prior) | 83.3% | 1.39 | 19.7 | −11.3% | 12 | Same sleeve path | Confirmed |

Full-book meta threshold sweep (v18b): thr=0.70 → WR 68.8% (n=16); thr≥0.75 → **0 trades**.

---

## 4. Working findings (reuse in next loops)

### Coulling / VPA
- **Light gates help quality:** `block_no_demand` + `require_commitment` + `allow_stopping_reclaim` → higher PF, lower DD (`v17b`).
- Prefer **soft size-down** on no-demand over hard blocks if you need capacity.
- **Stopping reclaim** is a useful alternate long path (not only `confirm_up`).

### Soros / strategy books
- Prefer sustained confirm / reclaim; **do not chase buying climax**.
- Options guide: treat climax as **risk/regime overlay**, not a new primary side model.
- Architecture stays locked: **primary = rules (side)** → **secondary = meta (whether / how much)**.

### GEX / volume meta (`poc_va_gex`)
- **`vol_z ≥ 1` or `≥ 2`** = strongest OOS WR lift on existing stock trades.
- Coulling no-demand alone ≈ flat; `book + vol_z` ≈ `vol_z` alone.
- Use **vol_z as primary** volume meta; no-demand only as soft veto.

Artifact: `models/poc_va_gex/artifacts/BOOK_VPA_META.json`  
Script: `models/poc_va_gex/research/book_vpa_meta.py`

### High-WR sleeve
- **APLD + IONQ** + QQQ trend + vol expand + block red-flag → **83.3% WR**, Sharpe 1.39, PF 19.7, n=12.
- Use as **satellite beside v15**, not a replacement.
- Small-cap / under-owned names fit POC/VA DNA better; edge may decay as they institutionalize.

### Process / desk
- Promote only if **all** pass-bar gates clear; **win rate alone is vanity**.
- Live desk: volume-first breakouts; 22 EMA drawdown zone; lost 200 EMA = structural break.
- Holdout / anti-overfit: freeze rules before lock; greedy auto-pick can FAIL (overfit warning).

---

## 5. Failed findings (do not repeat)

| ID | What we tried | Why it failed |
|----|---------------|---------------|
| F1 | Full 1H stack: climax + topping + effort (`v17`) | Over-filters; Sharpe/return collapse vs v15 |
| F2 | Promote PF/DD-only win without beating winner Sharpe | Capacity destroyed |
| F3 | Force **WR ≥ 90%** with more filters (`v18`) | Only thin n=2–4 “100%” spikes; **not reproducible** (`sample_noise`) |
| F4 | Meta threshold ≥ 0.75 on full book | Zero trades |
| F5 | Raw price ML as primary (`poc_va_xgb`) | Already `any_edge: false` — do not revive |

---

## 6. Model map (after this research)

| Path | Role |
|------|------|
| `models/poc_va_macdha/v15_meta_xgb/` | **WINNER** — best full-book Sharpe/capacity |
| `models/poc_va_macdha/v17_book_vpa/` | Full book gates — FAIL vs winner |
| `models/poc_va_macdha/v17b_book_vpa_light/` | Light Coulling overlay — quality↑ |
| `models/poc_va_macdha/v18_wr90/` | High-WR sniper sleeve (83% stable) |
| `models/poc_va_gex/` | GEX / `vol_z` meta path |
| `models/_shared/findings.jsonl` | Append-only durable log |
| `models/_shared/BOOK_FINDINGS.md` | Short index of book IDs |
| `models/poc_va_macdha/RESEARCH_NEXT.md` | Next lake experiments (A–D) |

---

## 7. Next iteration options

| ID | Experiment | Success if |
|----|------------|------------|
| A | Soft no-demand size×0.5 on v15 (no new hard gates) | Sharpe ≈ v15, PF/DD ≥ v15 |
| B | Climax/effort on **4H/1D only** as soft exit | Same bar + fewer climax losers |
| C | Wire `vol_z` meta into `poc_va_gex` (+ soft no-demand) | OOS WR/exp lift > 0 |
| D | Grow v18 sleeve: more under-owned small-caps + longer window | Durable WR≥90 with n≥40 OOS; else keep 83% sleeve |

---

## 8. CLI cheat sheet

```bash
cd /Users/syriljacob/Desktop/TradingAlgoWork

.venv/bin/python tools/findings.py working
.venv/bin/python tools/findings.py failed
.venv/bin/python tools/findings.py next

# Record after a run
.venv/bin/python tools/findings.py record \
  --family poc_va_macdha --version vN_name \
  --status auto --kind <kind> \
  --summary "..." \
  --metrics-json models/poc_va_macdha/vN_name/results.json
```

---

## 9. One-line summary

Books gave **useful quality filters** (Coulling light VPA, Soros “don’t chase climax”, commitment, `vol_z` for GEX). They did **not** beat `v15` on full-book Sharpe, and **90%+ WR is not a robust claim** yet — best stable high-WR product is an **83% APLD/IONQ sleeve** run beside the winner.
