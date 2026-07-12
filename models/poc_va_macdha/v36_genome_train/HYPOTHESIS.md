# v36_genome_train

**Parent:** `v23_devin_overlay` (frozen primary SIDE)  
**Method:** Evolve self-feedback train loop (15 epochs) + auditor gate  
**Trained:** secondary genome only — risk scale, signal threshold, soft DD knobs  

## Genome (accepted best)

| Knob | Value | Role |
|------|-------|------|
| risk_pct | ~0.130 | Scale |signal| vs 0.10 baseline (~1.3×) |
| min_confidence | ~0.545 | Zero weak |signal| bars |
| halt_dd / soft_dd | ~0.258 / 0.099 | Risk policy overlay |
| vol_z_min | ~0.15 | Documented meta (wrapper uses conf thr) |
| after_loss_mult | ~0.73 | Feedback size (policy file) |

## Claim

OOS window (2025-10→2026-07) improved vs seed during train (util 0.72→0.78, ret ~18%→24% on that slice).  
**Full-window CLAIM** only if PASS_BAR + multi-lock hold after formal rank — see `results.json` / evolve audit.

## Forbidden

- Does **not** replace primary rules with end-to-end ML  
- Options auto-promote: no  
