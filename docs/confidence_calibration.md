# Calibrated Live Confidence

The live plan now exposes a fail-closed `confidence` object with `ENTER`,
`WATCH`, and `ABSTAIN` states. The legacy `blended_confidence` value remains
for compatibility, but it is a heuristic score and must not be treated as a
probability.

## Main-model calibrators (honest policy — no cheating)

Rebuild / audit with:

```bash
.venv/bin/python tools/calibrate_main_models.py
```

Policy:

1. Fit isotonic only when sequential OOS **Brier and log-loss improve** vs raw.
2. If isotonic hurts, **do not force it**. Prefer **identity** map (raw = calibrated)
   with ENTER/WATCH tuned on OOF expectancy (bootstrap p05 > 0).
3. Never activate when confidence has no discrimination or ENTER expectancy ≤ 0.
4. **Runtime fails closed**: no silent `fallback_identity`. Missing artifact →
   `confidence.state = ABSTAIN` (not a fake ENTER).
5. `v65_spec_*` / universal specialists **inherit** `v39d_confluence` only when
   they lack their own active file (documented DNA alias). Own specialist maps
   win when evidence supports them.
6. Portfolio delta is 0 for these artifacts: calibration remaps live ENTER bands,
   not the historical backtest path.

Active artifacts live under `runs/calibration/active/<model>.json`.

## Timeframes (horizons)

Model selection and confidence thresholds are horizon-aware:

| Horizon | Meaning | Ranker bars | Default ENTER tilt |
|---------|---------|-------------|--------------------|
| `day` | Intraday / same-session | 1H windows | slightly lower bar |
| `swing` | Multi-day (default) | 1D windows | baseline (0.50 / 0.60) |
| `position` | Weeks–months | longer 1D | higher bar |

Use:

```bash
.venv/bin/python tools/live_plan.py --symbol TSLA --horizon day --json
.venv/bin/python tools/analysis_agent.py --symbol TSLA --horizon swing --json
.venv/bin/python tools/symbol_ranker.py rank TSLA --horizon day --quick
```

When `--model` is empty/`auto`, the **confidence ranker**
(`model_registry.select_model_for_confidence`) scores router candidates for that
horizon and optionally probes live raw probability so the desk can pick the
model with the highest confidence — not just the highest prior.

`router_confidence` is trust in the *model pick* (evidence depth + score gap +
horizon fit). It is **not** trade ENTER probability; execution still requires
calibrated `confidence.state == ENTER` plus readiness gates.

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
