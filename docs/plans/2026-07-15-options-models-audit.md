# Options Models Audit — Kill / Revive / Hold

**Date:** 2026-07-15  
**Lens:** Research-to-production vol program + current equity champions  
**Sources:** `OPTIONS_WINNER.json`, `runs/EVOLVE_RESULTS_SUMMARY.md`, `tools/feedback_loop_opts.py`, model dirs under `models/poc_va_macdha/*opts*`

---

## Executive verdict

| Track | Status | Action |
|-------|--------|--------|
| **Directional synthetic opts (v22–v35)** | Research-only; thin n on $1k evolve | **Hold** frozen OOS champ; **do not** auto-promote |
| **Vol relative-value (IV–RV / surface)** | Missing until Phase 1 | **Build new** — not a revival of opts signal engines |
| **Live desk structure** | `options_picker` + risk modes | **Keep** as directional path |
| **GEX** | Live context / risk | **Keep** as feature, not sole alpha |

---

## Frozen champion

**OPTIONS_WINNER:** `v35_softstruct_bag8`

- Selection: best mean OOS across pure holdout + walk-forward folds
- Interaction finding: bag8 **without** soft-structure overlay fails OOS; weak-structure downsizing is the safety
- Full-window vanity metrics exist but **must not** drive promotion
- `$1k` evolve screen: THIN claim — trust prior OOS artifact more

**Live desk note (stale in options-plan PLAYBOOK):** route still mentions `v29_coldstart_opts` / `v39b` in places. Align copy to:

- Equity timing: desk routing / WINNER path (currently dual-sleeve era — do not hardcode stale ids without reading `DESK_ROUTING.json`)
- Options structure OOS: `v35_softstruct_bag8` per `OPTIONS_WINNER.json`
- Structure execution: `options_picker` only

---

## Per-model ranking

### Revive (research mutations only)

| Model | Why | Next experiment |
|-------|-----|-----------------|
| **v35_softstruct_bag8** | Frozen OOS champ; soft structure is the edge | Mutate `struct_weak_mult`, DTE, bag membership with **min_trades≥12** pure OOS |
| **v30_feedback_pro** | Top of $1k evolve screen (still THIN) | Only if n≥12 folds; surgical narrative gates |
| **v28_feedback_opts** | Surgical FOMC∧VIX learning from MU autopsy | Keep as narrative gate library, not primary engine |

### Hold (archive, do not delete)

| Model | Why |
|-------|-----|
| v32_soft_react_opts | Soft-structure lineage |
| v34_bag6_opts | Prior OOS baseline beaten by v35 |
| v29_coldstart_opts | Historical live variant; still referenced in UI copy |
| v26_opts_evolve | Evolution ancestry |
| v22_opts_live / v22_opts_agg / v22_opts_hunt | First live opts stack; robust backtest UI |
| v22_robust_vol_only | Vol-only experiment — **not** Phase 1 surface science |
| v21_mstr_tsla_opts | Narrow bag research |

### Kill path (do not schedule new loops)

| Model | Why |
|-------|-----|
| Full-window “best ret” variants without OOS | False discovery risk (White / PBO) |
| Broad narrative size-down (pre-surgical v27 lessons) | Cuts winners; only FOMC∧elevated VIX matched MU blowup |
| Any model auto-promoted from `evolve_full_options` $1k thin-n screen | Explicit “Never auto-promote” in EVOLVE_RESULTS_SUMMARY |
| Quote-only mystery IV without package PnL | Literature + report: flow/package > static quotes |

### New build (preferred over reviving vol-only opts engines)

| Workstream | Replaces the need for |
|------------|----------------------|
| `rv_har` + `options_surface` + `features_vrp` | Ad-hoc IV inside each signal_engine |
| `vol_package_score` templates | Free-form chain search |
| Package backtests Phase 2 | Synthetic naked premium vanity runs |

---

## Feedback-loop hygiene

`tools/feedback_loop_opts.py`:

- Keep for **directional** opts autopsy → hypothesis → backtest
- Require `min_trades` floor before “winner” language
- Do **not** mix with IV–RV package scoring until shared cost model exists
- Record failure class: macro / structure / liquidity / regime — not only ret

---

## Desk routing recommendations

1. **Directional mode (default):** live_plan side + options_picker structure + risk_manager  
2. **Vol package mode (research):** `vol_package_score` panel — informational; never sets `OPTIONS_ATTACK` alone  
3. **GEX:** gate size / skip, not primary entry  
4. **Capital $1k:** debit spreads only; short vol packages require explicit larger capital + margin policy (out of scope)

---

## Acceptance for this audit

- [x] OPTIONS_WINNER frozen identity documented  
- [x] Kill vs revive vs hold table  
- [x] New vol feature stack preferred over expanding thin opts engines  
- [ ] PLAYBOOK string in `options-plan/route.ts` updated to v35 + dual-sleeve era (done in same PR as desk wire)
