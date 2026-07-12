# Evolution pipeline phases (final)

Status as of finalize module. CLI: `tools/evolve_pipeline.py`.

| Phase | Command | Output | Promote? |
|-------|---------|--------|----------|
| 0 Integrity | (always on) | claim levels, cache keys, PASS_BAR | — |
| 1 Rank farm | `rank --track equity\|options` | `runs/evolve_*/LEADERBOARD.md` | Equity CLAIM only |
| 2 Feedback loop | `loop --gens N` | mutations + gen scores | Equity CLAIM only |
| 3 Options research | `rank --track options` | synthetic BS board | **Never** auto |
| 4 Meta MLP | `meta` | `META_RECIPE.json` | Secondary size/skip only |
| Finalize | written after rank/loop | `FINALIZE.md` | Manual WINNER update |

## Frozen defaults (do not silent-replace)

- Equity desk / WINNER: see `models/poc_va_macdha/WINNER.json` (`v23_devin_overlay`)
- Options research default: `models/poc_va_macdha/OPTIONS_WINNER.json` (`v35_softstruct_bag8`)

## Smoke vs full-window

Smoke ranks used `--quick` (late window ~1y, thin bag) → low ret / RESEARCH.  
Full ranks use 2024-08→2026-07 + winner bags for honest comparison.
