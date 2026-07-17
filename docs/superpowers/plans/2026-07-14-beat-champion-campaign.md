# Beat Champion Campaign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run a 3-bet sequential campaign that freezes `v39d_confluence` and tries meta-ledger, exit/size mutations, then macro soft-size — promote only on lockbox multi-lock.

**Architecture:** Shared harness (`tools/feedback_loop_beat_champion.py`) freezes baseline hunt+lockbox, runs bets in order, stops on first promote or after 3 fails. Thin model wrappers for Bet 1/3; Bet 2 uses config-grid variants of v39d.

**Tech Stack:** Python 3, existing `dynamic_model_rank` / `dmr.run_one`, scikit-learn logistic, pandas, unittest.

**Spec:** `docs/superpowers/specs/2026-07-14-beat-champion-campaign-design.md`

---

## File map

| Path | Role |
|------|------|
| `tools/feedback_loop_beat_champion.py` | Campaign driver: baseline, bets, gates, STATE, LEADERBOARD |
| `tests/test_beat_champion_gates.py` | Unit tests for multi-lock gates + kill rules |
| `models/poc_va_macdha/v61_meta_ledger/` | Bet 1 wrapper + trained secondary meta |
| `tools/train_v61_meta_ledger.py` | Train secondary logistic from train-window ledger |
| `models/poc_va_macdha/v62_macro_softsize/` | Bet 3 soft-size overlay |
| `runs/beat_champion_v1/` | STATE.json, LEADERBOARD.md, artifacts |

---

### Task 1: Gate helpers + unit tests

**Files:**
- Create: `tests/test_beat_champion_gates.py`
- Create: gate helpers inside `tools/feedback_loop_beat_champion.py` (importable)

- [ ] **Step 1:** Implement `passes_promotion_gates(candidate, baseline, *, min_n_lockbox=10)` matching design multi-lock.
- [ ] **Step 2:** Unit tests: promote when all better; fail when ret equal; fail when dd much worse; fail on low n / error.
- [ ] **Step 3:** Run tests green.

### Task 2: Campaign harness skeleton

**Files:**
- Create: `tools/feedback_loop_beat_champion.py`

- [ ] **Step 1:** Constants: bag, dates, cash, OUT, train/test splits, PROMOTION_GATES.
- [ ] **Step 2:** `_run(model, start, end, tag, cash)` via `dmr.run_one(..., source="local", interval="1H", force_1d=False)`.
- [ ] **Step 3:** Freeze baseline hunt + lockbox; write partial STATE.
- [ ] **Step 4:** CLI: `--cash`, `--baseline-only`, `--from-bet`, `--skip-bet1` etc.

### Task 3: Bet 1 — meta ledger

**Files:**
- Create: `tools/train_v61_meta_ledger.py`
- Create: `models/poc_va_macdha/v61_meta_ledger/`

- [ ] **Step 1:** Run v39d train window; collect `candidates.csv` from run artifacts.
- [ ] **Step 2:** Fit logistic on `f_*` + meta_proba/adj_proba → `label`; save joblib + feature list + p_skip.
- [ ] **Step 3:** Wrapper engine: load v39d, after generate multiply positions by soft size from secondary model (or re-implement size gate at entry if wrap of series is too coarse — prefer entry-time if possible).
- [ ] **Step 4:** Harness runs hunt + lockbox; promote or fail.

**Note:** Soft size on full signal series is acceptable v1 if entry-time injection is too invasive: scale target positions by predicted quality of latest candidate; document limitation.

### Task 4: Bet 2 — exit/size grid

**Files:**
- Modify harness only; use temp model dirs or existing `v39d_confluence_tight_stop_all`

Pre-registered grid (≤7):

1. `stop_atr=1.0` all symbols (tight_stop_all pattern)
2. `stop_atr=1.2`
3. `stop_atr=1.0`, `trail_atr=2.0`
4. `signal_scale` via wrapper if needed — or skip if not in routing
5. `max_loss_pct` tighter where present
6. Baseline-equivalent control (should not promote)
7. Optional `stop_atr=0.8`

- [ ] **Step 1:** Materialize variants by copying v39d and patching `_ROUTING` stop_atr (same as mutator).
- [ ] **Step 2:** Hunt-rank; lockbox only best; promote or fail.

### Task 5: Bet 3 — macro soft size

**Files:**
- Create: `models/poc_va_macdha/v62_macro_softsize/`

- [ ] **Step 1:** Load v39d engine; compute VIX/SPY regime from data_map; multiply signals by mult in [0.25, 1.0].
- [ ] **Step 2:** If SPY missing → clean fail.
- [ ] **Step 3:** Hunt + lockbox; promote or plateau.

### Task 6: End state

- [ ] Write LEADERBOARD + STATE with plateau or promoted_best.
- [ ] Brief note in run dir; do not auto-edit AGENTS.md champion without human confirm.

---

## Commands

```bash
.venv/bin/python -m unittest tests.test_beat_champion_gates -v
.venv/bin/python tools/feedback_loop_beat_champion.py --cash 1000 --baseline-only
.venv/bin/python tools/feedback_loop_beat_champion.py --cash 1000
```

## Spec coverage

| Spec section | Task |
|--------------|------|
| §1 harness | Task 2 |
| §2 Bet 1 | Task 3 |
| §3 Bet 2 | Task 4 |
| §4 Bet 3 | Task 5 |
| §5 gates/kill/STATE | Tasks 1, 2, 6 |
