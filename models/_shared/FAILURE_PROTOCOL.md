# Failure Protocol — Research Finding Failed in Practice

When a finding from `findings.jsonl` or `EDGE_RESEARCH.md` is implemented and **fails** OOS / PASS_BAR:

## Do NOT

- Stack another AND filter and hope win rate rises
- Promote the version to WINNER
- Retrain on the full sample and call it fixed
- Switch to LSTM/transformers as primary side without new research

## Do (in order)

1. **Record the failure** with `tools/findings.py record --status fail` (link metrics path + what was tried).
2. **Classify the failure**
   - `label_mismatch` — ML labels ≠ actual trade PnL
   - `sample_noise` — too few trades / too short window
   - `overfit_specialist` — per-symbol tune dies OOS
   - `regime_break` — worked in one tape, not another
   - `cost_kill` — edge < costs/slippage
   - `wrong_hypothesis` — premise itself was wrong
3. **Re-research** (narrow):
   - Re-read LSE eval / walk-forward / meta-label pages + relevant SSRN
   - Diff failed approach vs last WORKING finding
   - Write a new hypothesis in `models/<family>/RESEARCH_NEXT.md` (overwrite or date-stamp)
4. **Design the next lake** (small complete fix), not an ocean rewrite.
5. Only then start `vN+1_*`.

## Escalation

After **3 failed attempts** on the same hypothesis class → stop coding. New `EDGE_RESEARCH` pass required before more versions.
