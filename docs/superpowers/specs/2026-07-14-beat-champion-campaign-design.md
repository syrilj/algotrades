# Beat Champion Campaign — Design Spec

**Date:** 2026-07-14  
**Status:** Approved (Approach 1, budget B, ladder D)  
**Champion:** `models/poc_va_macdha/v39d_confluence/`  
**Contract:** `EQUITY_WINNER_BAG`, `source=local`, `interval=1H`, cash `$1000`, window `2024-08-01` → `2026-07-11`

---

## Goal

Run a **hard-capped, sequential 3-bet campaign** to beat the frozen equity champion under a two-stage ladder:

- **Hunt (A):** same full-window contract as champion (screen / rank).
- **Promote (B):** walk-forward lockbox must multi-lock on return, Sharpe, and drawdown.

Stop at the **first promote**, or after **three clean fails**. Write a plateau report if nothing promotes. No secret fourth hybrid of failed bets without reopening scope.

This campaign does **not** target $1k → $1M. It targets a **verified modest beat** of `v39d_confluence` under the same research contract, with out-of-sample integrity.

---

## Success definition (ladder D)

### Hunt contract (screen)

| Knob | Value |
|------|--------|
| Model baseline | `v39d_confluence` |
| Codes | `EQUITY_WINNER_BAG` = TSLA.US, MU.US, SPY.US, IONQ.US, APLD.US, XLP.US, QQQ.US |
| Source | `local` |
| Interval | `1H` |
| Cash | `$1000` |
| Start / end | `2024-08-01` / `2026-07-11` |
| Metrics | `ret`, `dd`, `sharpe`, `n`, `wr`, `final` |

### Promote contract (lockbox)

| Knob | Value |
|------|--------|
| Train / fit window | `2024-08-01` → `2025-08-01` |
| Test / lockbox window | `2025-08-01` → `2026-07-11` |
| Same bag, source, interval, cash | as hunt |

Any model that requires fitting (meta-label, size map) **fits only on the train window**. Hyperparameters are pre-registered; only the pre-registered config may claim promote. No post-lockbox retuning.

### Multi-lock promote gates

A candidate **promotes** only if **all** of the following hold on the **lockbox** vs the **frozen baseline lockbox row** (not only full-window hunt):

1. `ret_candidate > ret_baseline`
2. `sharpe_candidate > sharpe_baseline`
3. `abs(dd_candidate) <= abs(dd_baseline) + 0.02` (not materially worse drawdown)
4. Absolute floors:
   - Hunt: `n >= 30`
   - Lockbox: `n >= 10`
   - `ret >= 0`, `abs(dd) <= 0.25`, `sharpe >= 1.0` (absolute sanity; champion is far above these)

Hunt multi-lock is **advisory** (logged, not sufficient for promote).

---

## Architecture overview

```
Shared harness (feedback_loop_beat_champion)
  ├─ Freeze baseline: hunt + lockbox rows for v39d_confluence
  ├─ Bet 1: v61_meta_ledger   (meta-label on candidate ledger)
  ├─ Bet 2: exit/stop/size grid on frozen v39d (≤7 configs; best hunt → lockbox)
  └─ Bet 3: v62_macro_softsize (macro soft size mult)
        ↓
STATE.json + LEADERBOARD.md
  stop on first promote OR after 3 fails → plateau report
```

**Reuse:**

- `tools/dynamic_model_rank.py` (`dmr.run_one`) / farm caching patterns
- Promotion style from `tools/feedback_loop_arete.py`
- `models/poc_va_macdha/_shared/candidate_ledger.py`
- `tools/evolve/macro_features.py` for Bet 3

**Out of scope:** trade-desk UI, market_runtime live, new primary signal family, tick/L2, stacking failed bets into a hybrid.

---

## §1 Shared promotion harness

### Runner

- Path: `tools/feedback_loop_beat_champion.py`
- Out dir: `runs/beat_champion_v1/`
- Artifacts: `STATE.json`, `LEADERBOARD.md`, optional per-bet `HYPOTHESIS.md` copies

### Behavior

1. Discover and freeze `v39d_confluence` baseline (hunt + lockbox).
2. Run bets in order: meta → exits/size → macro.
3. After each bet: score hunt + lockbox; apply promote gates on lockbox vs baseline lockbox.
4. If promote → write STATE, stop.
5. If fail → log reason, next bet (or plateau after third).

### Hard campaign rules

- Max **3 bets**, fixed order.
- Stop on first **promote**.
- No combining Bet 1+2+3 into an unregistered Bet 4.
- Every run logged with model id, tag, source, metrics, `promoted: bool`.

---

## §2 Bet 1 — candidate-ledger meta-label (`v61_meta_ledger`)

### Hypothesis

v39d’s primary side and candidates are good enough; losers are filterable from **point-in-time features at entry**. Secondary model on real ledger outcomes can skip or downsize without a new primary recipe.

### Architecture

```
v39d primary (frozen) → long_entry candidates
  → ledger features (f_*, meta_proba, adj_proba, …)
  → P(good trade | candidate) fit on train only
  → soft size: size *= g(p); skip if p < p_skip
  → same exits as v39d
```

### Data / labels

- Ledger: `CandidateLedger` → `candidates.csv` (`label` = 1 if `realized_r > 0`).
- Features: all `f_*` columns + `meta_proba`, `adj_proba`, `meta_sz`, `feat_m` available at entry.
- Label = strategy exit outcome, **not** fixed N-bar forward return.
- Fit only on train-fold candidates with non-empty labels.

### Pre-registered config

| Knob | Value |
|------|--------|
| Base | Frozen v39d path |
| Model | Logistic regression first (default); shallow XGB only if train CV shows logistic useless |
| Action | Soft size `g(p)` with skip below `p_skip` (pre-registered, e.g. 0.45) |
| Exits | Unchanged |

Diagnostic hard-skip vs soft-size may be logged; **only soft-size pre-registered config** may promote.

### Fail / pass

- Promote: lockbox multi-lock.
- Fail: gates fail, `n` floor fail, or train CV shows no lift → count Bet 1 used, proceed to Bet 2.
- No open feature shopping after first lockbox look.

### Deliverables

- `models/poc_va_macdha/v61_meta_ledger/` (wrapper signal engine + train artifact)
- Train helper if needed: `tools/train_v61_meta_ledger.py`
- Campaign row in LEADERBOARD

---

## §3 Bet 2 — exit / stop / size mutations only

### Hypothesis

Risk path (ATR stop, target, global scale) can multi-lock even when entry selection is saturated.

### Architecture

Frozen v39d **entries** unchanged. Mutation layer only:

- Stop ATR multiple
- Optional take-profit / trail
- Optional global `signal_scale`

### Grid discipline

- Pre-register **≤7** configs in campaign config / HYPOTHESIS before any Bet 2 run.
- Score all on **hunt**; send **only the single best hunt config** to lockbox.
- No second tweak after lockbox.

Prefer config/genome knobs and existing tight-stop patterns (`v39d_confluence_tight_stop_all`, evolve mutations) over new code.

### Fail / pass

- Promote: lockbox multi-lock vs baseline.
- Fail: best hunt member fails lockbox (or entire grid fails hunt floors).
- Skipped entirely if Bet 1 already promoted.

---

## §4 Bet 3 — macro soft-size (`v62_macro_softsize`)

### Hypothesis

Macro / cross-asset regime can **scale** risk without blocking entries. Soft size-down in hostile regimes improves risk-adjusted path. Hard macro gates are forbidden (Arete/v40 class failure).

### Architecture

```
v39d frozen entries + exits
  → MacroCrossAssetEngine features (causal)
  → size_mult = h(features) ∈ [size_floor, 1.0]  (default downsize-only)
```

### Causal contracts

- Lag returns before rolling beta/corr.
- Macro events: backward `merge_asof` only.
- Fit any size-map params on train fold only.
- Missing SPY/TLT/VIX (or required macro CSV) → **clean Bet 3 fail**, no invented mid-campaign proxies.

### Pre-registered config

| Knob | Value |
|------|--------|
| Overlay | Soft size only — no hard entry block |
| Floor | e.g. `size_mult ∈ [0.25, 1.0]` |
| Base | Frozen v39d |

### Fail / pass

- Promote: lockbox multi-lock.
- Fail: gates fail, data incomplete, or overlay is identity (no material size variation).
- After fail: campaign ends with plateau report.

---

## §5 Gates, kill rules, end-state artifacts

### Kill budget

| Event | Action |
|-------|--------|
| Bet promotes | Stop campaign; mark `promoted_best`; optional AGENTS.md note only after human confirm |
| Bet fails | Next bet |
| 3 fails | `plateau: true`; write short plateau section in LEADERBOARD |

### STATE.json schema (minimum)

```json
{
  "started_at": "...",
  "finished_at": "...",
  "baseline": {"hunt": {}, "lockbox": {}},
  "bets": [
    {"id": "bet1_meta_ledger", "status": "fail|promote|skipped", "hunt": {}, "lockbox": {}, "reason": "..."}
  ],
  "promoted": [],
  "promoted_best": null,
  "plateau": false,
  "promotion_gates": {}
}
```

### LEADERBOARD.md

- Cash, period, codes, source, interval
- Baseline hunt + lockbox rows
- Each bet hunt + lockbox + promote YES/NO + reason
- Final verdict: promoted model id **or** plateau summary

### Plateau report (if no promote)

One short section stating:

- All three bets failed multi-lock on lockbox
- Residual plateau is structural under OHLCV + 2y bag for this attack surface
- Do not auto-promote any hunt-only winner
- Optional next scope (tick/L2, longer history, capacity) is **out of this campaign**

### Explicit non-goals (campaign-wide)

- No new primary indicators as the promote path
- No OHLCV fake microstructure (v44/v60 class)
- No v42-style weak teachers in ensemble
- No high-WR vanity sleeve as “beat” if return/Sharpe fail
- No live capital deployment from this campaign alone

---

## Probability framing (not a promise)

| Outcome | Rough prior |
|---------|-------------|
| Modest verified promote | ~25–40% with disciplined execution |
| Large leap (2× return, same risk) | Low on this data class |
| Plateau after 3 fails | Material possibility — treated as a valid result |

---

## Implementation notes

- Prefer thin wrappers over forking 1000-line engines when possible.
- Tests: unit tests for gate logic + label/fit no-leakage contracts; full bag backtests are campaign runs, not CI.
- Disk is tight on the research machine — reuse caches; avoid unbounded run dirs.

---

## Approval record

- Success ladder: **D** (hunt A, promote B)
- Attack path: **sequenced** meta → exits/size → macro
- Budget: **B** (3 bets, stop at promote or after all fail)
- Approach: **1** (shared harness, sequential)
- Sections §1–§4 approved by user; §5 included in full write-up; user cleared to start implementation
