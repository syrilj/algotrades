# Evolution pipeline

Constraints-first automation for ranking and improving `poc_va_macdha` models.

| Phase | What | Promote? |
|-------|------|----------|
| 0 | Data tracks, dual bars (THIN/RESEARCH/CLAIM), content cache | — |
| 1 | `rank` — screen + deep + multi-lock | Equity CLAIM only |
| 2 | `loop` — gens + constrained mutations | Equity CLAIM only |
| 3 | Options track (synthetic BS) | Never auto |
| 4 | `meta` — walk-forward MLP recipe | Secondary only |

CLI: `tools/evolve_pipeline.py`
