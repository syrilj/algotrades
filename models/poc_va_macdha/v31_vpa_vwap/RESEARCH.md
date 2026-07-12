# RESEARCH: VPA + VWAP institutional flip stack

**Status:** research-first · **not** live-promoted (80% WR gate **FAIL** on pure VPA flips)  
**Date:** 2026-07-12  
**Method:** parallel explore agents (VWAP DNA · VPA/feedback DNA · anti-overfit design)

---

## 1. What “truth” means (institutions + algos)

| Layer | Question | Source in repo |
|-------|----------|----------------|
| **POC / Value Area** | *Where* did volume trade? | `poc_va_*` DNA |
| **Swing VWAP** | *Where* is the algo/session peg? | `_engine_template.dynamic_swing_anchored_vwap` |
| **VPA (Coulling)** | *Is effort real?* Volume vs spread | `v30_flip_any/vpa.py`, Coulling book |
| **vol_z** | *How unusual* is participation? | `VOLUME_Z_META`, v23 overlay |

**Law (Coulling):** volume = effort, price spread = result. Harmony confirms; anomaly = trap / absorption.

**Law (algos):** price gravitates to **VWAP** (and profile POC). Flips that fight the peg without volume are noise.

**Do not AND-stack all of these hard** — that is the v17 over-filter trap. Soft combine:

```
SIDE trigger   = VPA call/put (effort–result)
PEG bias       = soft: prefer with VWAP (OR, not hard kill)
PARTICIPATION  = soft size: vol_z / vol expand
REGIME         = soft or surgical only (FOMC∧VIX)
```

---

## 2. What 30+ models already taught us

### Works
- **Primary = rules** (specialists), meta/size secondary  
- **Light VPA** (no_demand soft, stopping reclaim) — quality  
- **vol_z soft boost** (v23 WINNER equity)  
- **Surgical FOMC∧VIX** — not broad FEAR  
- **Pure OOS elects options default** (not full-window peaks)  
- **VWAP helps some names** (APLD/SPY/IONQ above); **hurts TSLA/MU** hard-gated  

### Fails OOS / overfit
- Full Coulling climax stack on 1H  
- Pure VPA auto flips as full book (WR ~39–50%, not 80%)  
- Hard multi-AND volume gates (capacity death)  
- Broad narrative size-down  
- Cooloff+streak without mean-OOS win  
- Force 80–90% WR with n≪40  

### Honest WR reality
| Book | Typical WR | n | Note |
|------|------------|---|------|
| Pure VPA flip standard | ~39% | large | FAIL 80 gate |
| Pure VPA sniper | ~50–60% | smaller | FAIL 80; better PF |
| Equity WINNER v23 | ~65% | ~92 | Risk-adj, not 80 |
| High-WR sleeve APLD/IONQ | ~83% | ~12 | Satellite only |

**≥80% WR = aspirational sleeve with n≥40 OOS — not current full auto product.**

---

## 3. $1k → $1M in a month

**Not a valid backtest claim.**

- Capital **locks** in options; you cannot reinvest full equity every day.  
- Repo realistic ceilings are multi-month/year paths, not 1000×/30d.  
- Extreme compounds are path lottery + synthetic pricing.  

**Realistic process:** paper → small live (5–10% risk) → autopsy → one hypothesis → pure OOS → scale only after n≥40 with stable expectancy.

Your discretionary TSLA/MSTR flips can still print large months; **that edge is you**, not an unvalidated robot at 80% WR.

---

## 4. Architecture for the next model (anti-overfit)

### Frozen for research version `v31_vpa_vwap`

| Piece | Spec |
|-------|------|
| Universe | Any codes in config |
| CALL | VPA strength (stop reclaim / spring / no-supply test) **and** soft VWAP bias (above OR reclaim toward VWAP) |
| PUT | VPA weakness (top fail / upthrust / no-demand die) **and** soft VWAP bias (below OR reject VWAP) |
| Hard blocks only | no_demand on CALL; buying_climax chase; effort_anomaly optional soft |
| Size | Aggressive flip OK, but split across max_open; vol_z soft mult |
| Hold | 1–5 days; exit on reverse VPA or VWAP flip |
| Validation | Pure OOS folds + PASS_BAR spirit (n, PF, DD) — **WR reported, not sole promote** |

### Promote only if
1. Mean pure-OOS score beats incumbent options/flip research baseline  
2. n sufficient (target ≥40 closed on full or multi-fold sum)  
3. Holdout WR does not collapse >15pp vs discovery  
4. **If claiming 80% WR:** OOS WR≥80 **and** n≥40 **and** PF≥1.2  

---

## 5. Continuous feedback loop (keep forever)

```
Live / BT fill
    → Autopsy (why lose: VPA tag + VWAP side + vol_z + regime)
    → One hypothesis (HYPOTHESIS.md)
    → Backtest full window (capacity check only)
    → Pure OOS multi-fold re-rank
    → findings.jsonl promote | fail
    → Live size mult only from journal (never silent SIDE retune)
```

**3 fails same class → stop coding, re-research EDGE.**

Harness: `tools/feedback_loop_vpa_vwap.py`  
State: `runs/poc_va_v31_feedback/LOOP_STATE.json`

---

## 6. Parallel workstreams (next sprints)

| ID | Stream | Deliverable |
|----|--------|-------------|
| W1 | VPA+VWAP soft stack (this version) | Engine + OOS baseline |
| W2 | vol_z soft size only | Ablation vs W1 |
| W3 | Sniper sleeve n≥40 path | Expand window/bag after freeze |
| W4 | Live VPA scan API (tags only) | Desk research tab — **not** 80% live trade |
| W5 | Sector RS + weekly watchlist | Next-week scan research |
| W6 | Realized-option cooloff honesty | If used, OOS must beat |

**Priority:** W1 → W2 → W4 → W3. Do not force 80% WR by stacking filters.

---

## 7. Live desk (when ready)

| Tab | Gate |
|-----|------|
| **VPA Scan (research)** | Always OK — show CALL/PUT bias + VWAP peg + tags |
| **Live trade auto** | Only after 80% WR **or** user accepts PF-based promote without 80% |

Week-ahead options flow + sector rotation = **W5** (data dependency).

---

## Bottom line

1. **VWAP pegs where algos lean; VPA says if volume is real** — combine soft.  
2. **30+ models already encode this**; pure flips are not 80% WR yet.  
3. **Research first, feedback loops forever, pure OOS elects.**  
4. **$1k→$1M/month is not a backtest KPI.**  
5. Build **v31_vpa_vwap** + loop harness; promote only under written bars.

---

## 8. Loop 1 results (2026-07-12)

Harness: `tools/feedback_loop_vpa_vwap.py` → `runs/poc_va_v31_feedback/LOOP_STATE.json`

| Ablation | Mean OOS score | Mean OOS ret | Mean WR | Fold wins | 80% gate |
|----------|----------------|--------------|---------|-----------|----------|
| **v31_hard_peg** | **0.586** | **+55.7%** | 39% | 3/5 | FAIL |
| v31_soft_vwap | 0.410 | +37.4% | 36% | 1/5 | FAIL |
| baseline_vpa_only | 0.174 | +15.1% | 36% | 0/5 | FAIL |
| v31_sniper_soft | −0.023 | −1.6% | **50%** | 1/5 | FAIL |

### Lessons from loop 1
- **VWAP helps OOS return** (hard peg beat VPA-only) — algo peg is real.  
- **Hard peg won score** but WR still ~39% — not 80% live bar.  
- **Sniper raises WR (~50%)** but killed mean score on this bag (thin + bad folds).  
- Soft VWAP is second; keep both as lakes for loop 2 (hard peg risk: name-dependent overfit — DNA said TSLA/MU hate hard VWAP).  
- **No Live 80% tab** until mean WR≥80 with adequate n.

### Loop 2 candidates (executed)
1. Soft peg + hard peg only on DNA-friendly symbols (not TSLA/MU).  
2. vol_z≥1 hard size floor only on CALL reclaim.  
3. Scanner UI (research) separate from promote.

---

## 9. Loop 2 results — symbol-aware VWAP DNA (2026-07-12)

**Hypothesis:** hard peg only on DNA-friendly names (APLD/SPY/IONQ); soft majors; **off** TSLA/MU.

| Ablation | Mean OOS score | Mean OOS ret | Mean WR | Fold wins | 80% gate |
|----------|----------------|--------------|---------|-----------|----------|
| **v31_hard_peg** (global) | **0.586** | **+55.7%** | 39% | 3/5 | FAIL |
| v31_soft_vwap | 0.410 | +37.4% | 36% | 1/5 | FAIL |
| **v31_symbol_dna** | 0.327 | +29.6% | 37% | 0/5 | FAIL |
| baseline_vpa_only | 0.174 | +15.1% | 36% | 0/5 | FAIL |
| v31_sniper_soft | −0.023 | −1.6% | 50% | 1/5 | FAIL |

### Lessons from loop 2
- Symbol DNA **beats VPA-only** (+29.6% vs +15.1% mean OOS ret) — name policies help.  
- DNA **does not beat** global soft or global hard on this bag (many soft names; few hard specialists).  
- Still **not 80% WR** → research Scan tab only; no Live auto.  
- DNA remains useful as **scan UI labels** (hard/soft/off tags) even when not OOS champion.

### Artifacts
- DNA: `vwap_dna.json`  
- Engine flag: `use_symbol_dna` in hunt_config  
- Loop: `tools/feedback_loop_vpa_vwap.py --loop2`  
- Desk: `/scan` + `GET/POST /api/vpa-scan` + sector RS via `--with-sectors`  
- Sector tool: `tools/sector_watchlist.py`

### Loop 3 candidates
1. Hard peg only on bag with more DNA-hard names (APLD/SPY/IONQ-heavy) — separate sleeve.  
2. Hybrid: global soft size + DNA hard **block** only (no soft mult table).  
3. Paper discretionary checklist using Scan tab + weekly sector leaders.
