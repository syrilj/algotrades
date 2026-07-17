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

## Self-healing autonomous research

`tools/self_healing_feedback_loop.py` is the resumable controller for long
local searches. It is an evolutionary/bandit-style optimizer, not an online
trading RL agent:

- reward comes only from the purged rolling validation folds;
- mutation failures and score deltas persist in `MODEL_MEMORY.json`;
- the selected research parent is frozen under the run directory each cycle;
- checkpoints, stale-lock recovery, retry budgets, disk/runtime/load limits,
  and graceful stop files make long desktop runs resumable;
- candidates are never written to `models/` and never deployed automatically;
- the final lockbox is not read during learning. `--qualify-final` consumes it
  once, only after the learning budget ends, and never feeds the result back.

Start a bounded local run:

```bash
.venv/bin/python tools/self_healing_feedback_loop.py run \
  --base v39b_live_adapt \
  --cash 1000 \
  --generations-per-cycle 1 \
  --max-variants-per-generation 8 \
  --max-cycles 10 \
  --max-runtime-hours 8
```

Run without `--qualify-final` while developing or tuning the search. Use a
genuinely new forward window for the eventual qualification whenever possible;
the repository's historical 2026-Q2 lockbox has already been inspected by
earlier research and should not be described as pristine evidence.

Inspect or stop a run safely:

```bash
.venv/bin/python tools/self_healing_feedback_loop.py status
.venv/bin/python tools/self_healing_feedback_loop.py stop
.venv/bin/python tools/self_healing_feedback_loop.py clear-stop
```

The checkpoint is `runs/self_healing_feedback/STATE.json`. A stopped or
resource-paused run resumes from that checkpoint with the same `run` command.
There is intentionally no "run until edge" condition: repeated historical
search cannot prove a live edge, so the terminal conditions are compute budget,
integrity failure, explicit stop, and later forward/paper-trading evidence.

### Champion-relative v72 search

The expanded search mode starts from the promoted v72 hierarchical book and
mutates controls its engine actually consumes: `core_scale`,
`both_core_frac`, `max_weight`, and `sniper_min_conf`. Every cycle reruns a
frozen v72 control on the identical folds. Candidate trades/equity are hashed;
parameter mutations with identical behavior are rejected as no-ops.

```bash
.venv/bin/python tools/self_healing_feedback_loop.py run \
  --run-dir runs/self_healing_v72_round2 \
  --search-mode v72_sleeve \
  --base v72_dual_sleeve \
  --cash 1000 \
  --max-variants-per-generation 6 \
  --max-cycles 3 \
  --max-runtime-hours 2
```

This mode still uses rolling validation only and does not open the final
lockbox or modify live routing. A candidate is marked `beat_champion=true`
only when it has a non-trivial score advantage, sufficient rank confidence,
no failure tags, and behavior different from the control.
