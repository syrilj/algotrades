# evolve_direction_v1

Honest, hard-to-overfit evolution pipeline for direction-equity strategies.

## Pipeline

1. `tools/snapshot_data.py snapshot` — refresh 1h/1d parquet cache and write `data_cache/MANIFEST.json`.
2. `tools/regime.py build` — build `models/_shared/regime/regime_daily.parquet`.
3. `runs/evolve_direction_v1/driver.py phase0` — re-run the current champion through folds + audit.
4. `runs/evolve_direction_v1/driver.py campaign` — smoke test: 2 generations of constrained direction variants.

## Key files

- `tools/evolve/folds.py` — fold calendar, OOS slicing, per-fold metrics.
- `tools/evolve/costs.py` — slippage realism, stress tests, `probe_slippage_applied`.
- `tools/evolve/stats.py` — sign-flip permutation, deflated Sharpe ratio.
- `tools/evolve/direction_report.py` — hit@k, MFE/MAE, regime-sliced expectancy.
- `tools/evolve/validate_run.py` — Monte-Carlo DD and bootstrap Sharpe validation.
- `tools/evolve/audit_gen.py` — 13-gate audit, `AUDIT.json` and `AUDIT.md`.
- `tools/evolve/loop_core.py` — fold runner, fitness objective, trial logger.
- `tools/evolve/mutations.py` — `DIRECTION_MUTATION_MENU` and `spawn_direction_variants`.
- `tools/direction_report.py` — CLI for `DIRECTION.json`.
- `models/_shared/OBJECTIVE.json` — selection objective.
- `models/_shared/AUDIT_GATES.json` — audit gates.
- `models/_shared/REGIME_SPEC.json` — regime build spec and sector map.

## Tests

```bash
.venv/bin/python -m pytest tests/evolve_v1 -q
```

## Design notes

- Selection uses the OBJECTIVE.json fitness, not `model_registry.score_metrics`.
- LOCKBOX is not scored during evolution; it is opened once per promotion.
- `AUDIT_GATES.json` gate 9 requires Track B (1D) evidence; the 1H-only v39b baseline
  is not expected to pass it.
