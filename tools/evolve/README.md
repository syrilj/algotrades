# Evolution pipeline

Constraints-first automation for ranking and improving `poc_va_macdha` models.

## Robust ranking and failure learning

`model_feedback.py` ranks models on comparable evaluation contracts. The score
starts with mean utility and subtracts penalties for window instability,
negative OOS performance, failed multi-lock checks, and incomplete confidence.
Every ranked row includes `rank_score`, `rank_confidence`, `rank_components`,
and a structured `failure_profile` with evidence and suggested next actions.

The evolution loops persist those profiles and mutation score deltas in
`runs/evolve_memory/MODEL_MEMORY.json`. Later generations prioritize mutations
whose declared failure targets match recurring problems, plus a bounded reward
for historically positive deltas and an exploration bonus. Parent and mutation
runs always use the same dates and symbol bag before they are compared.

Inspect accumulated feedback:

```bash
.venv/bin/python tools/evolve_pipeline.py feedback
.venv/bin/python tools/evolve_pipeline.py feedback --model v39d_confluence
.venv/bin/python tools/evolve_pipeline.py feedback --json
```

| Phase | What | Promote? |
|-------|------|----------|
| 0 | Data tracks, dual bars (THIN/RESEARCH/CLAIM), content cache | — |
| 1 | `rank` — screen + deep + multi-lock | Equity CLAIM only |
| 2 | `loop` — gens + constrained mutations | Equity CLAIM only |
| 3 | Options track (synthetic BS) | Never auto |
| 4 | `meta` — walk-forward MLP recipe | Secondary only |

CLI: `tools/evolve_pipeline.py`
