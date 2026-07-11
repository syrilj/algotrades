# Shared Model Improvement Playbook

Every new model version under `models/<family>/vN_*` must follow this module.
Findings live in `findings.jsonl`. Failures trigger the re-research loop — do not stack more filters blindly.

## Architecture rule (locked)

```
Primary (rules) → chooses SIDE
Secondary (meta) → chooses WHETHER / HOW MUCH
Risk → stops, trails, Kelly/buckets
```

Do **not** replace primary side with raw price ML (LSTM/XGB on close). That path already failed once (`poc_va_xgb`, `any_edge: false`).

## Promote only if ALL OOS pass bars clear

See `PASS_BAR.json`. Win rate alone is vanity.

## New version checklist

1. Copy from current WINNER engine (or `_engine_template.py`), not from a random old variant.
2. Read `findings.jsonl` — apply WORKING findings; avoid FAILED approaches unless redesigned.
3. Freeze a hypothesis in `HYPOTHESIS.md` inside the version folder (1 paragraph).
4. Backtest with walk-forward / longer window when claiming edge.
5. Write `results.json` + append a finding via `tools/findings.py`.
6. If FAIL → follow `FAILURE_PROTOCOL.md` (re-research, do not ship).
7. If PASS → update `WINNER.json` + `MODEL.md` row.

## Shared files

| File | Role |
|------|------|
| `PLAYBOOK.md` | This doc — process every model follows |
| `PASS_BAR.json` | Numeric promotion gates |
| `findings.jsonl` | Append-only success/fail log |
| `FAILURE_PROTOCOL.md` | What to do when a finding fails in practice |
| `templates/HYPOTHESIS.md` | Per-version hypothesis stub |
| `templates/VERSION_README.md` | Per-version README stub |

## CLI

```bash
cd /Users/syriljacob/Desktop/TradingAlgoWork

# List durable findings
.venv/bin/python tools/findings.py list

# Record a result after a backtest / research run
.venv/bin/python tools/findings.py record \
  --family poc_va_macdha --version v15_meta_xgb \
  --status fail --kind meta_label \
  --summary "OOS expectancy lift <= 0" \
  --metrics-json models/poc_va_macdha/v15_meta_xgb/results.json

# Next actions when something failed
.venv/bin/python tools/findings.py next
```
