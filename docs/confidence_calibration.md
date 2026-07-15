# Calibrated Live Confidence

The live plan now exposes a fail-closed `confidence` object with `ENTER`,
`WATCH`, and `ABSTAIN` states. The legacy `blended_confidence` value remains
for compatibility, but it is a heuristic score and must not be treated as a
probability.

## Build a candidate artifact

Use completed candidate ledgers from the reconciled local-data runs:

```bash
python3 tools/evolve/calibration.py \
  --input runs/poc_va_dynamic_rank/runs/v39d_confluence/baseline_manifest_v1__daily__c1000/artifacts/candidates.csv \
  --output runs/calibration/candidates/v39d_confluence.json \
  --model v39d_confluence --source local --interval 1H
```

The command produces sequential out-of-sample Brier score, log loss, ECE,
reliability bins, action-band expectancy, and a bootstrap lower bound. It
always writes `status: candidate`. `--activate` additionally requires explicit
candidate and baseline portfolio Sharpe/drawdown arguments and rejects the
artifact unless every calibration and portfolio gate passes.

The runtime reads only:

```text
runs/calibration/active/v39d_confluence.json
```

or the path in `CONFIDENCE_CALIBRATION_PATH`. A missing, inactive, mismatched,
or failed artifact produces `ABSTAIN`.

## Causal Feature Experiments

Run one approved feature family against the raw candidate probability. The
join is backward-only, so an entry can use only the most recent bar at or
before its timestamp:

```bash
.venv/bin/python tools/evolve/feature_validation.py \
  --input runs/poc_va_dynamic_rank/runs/v39d_confluence/baseline_manifest_v1__daily__c1000/artifacts/candidates.csv \
  --bar-source data_cache/1h \
  --family ohlcv_effort \
  --output runs/calibration/candidates/v39d_ohlcv_effort.json \
  --baseline-sharpe 2.82 --baseline-dd -0.134
```

The feature candidate must improve Brier score and log loss, pass ECE on both
sequential OOF data and the locked final holdout, and pass the portfolio gates.
A partial improvement remains research-only.

## Research controls

Create a locked experiment manifest before testing a feature family:

```bash
python3 tools/evolve/confidence_research.py \
  --output runs/calibration/manifests/pivot.json \
  --feature-family confirmed_pivot
```

Only `confirmed_pivot` and `ohlcv_effort` are currently allowed. The feature
implementations use bars available at the decision timestamp and do not claim
true delta or order-book information. LSE ticks are recorded separately for
future shadow research.

## Shadow outcomes

Live plans append to `runs/live_confidence/shadow_decisions.jsonl`. Inspect or
settle an event with:

```bash
python3 tools/confidence_shadow.py
python3 tools/confidence_shadow.py --settle EVENT_ID --outcome 0.012
```
