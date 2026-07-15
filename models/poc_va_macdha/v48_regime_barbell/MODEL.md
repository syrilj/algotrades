# v48 Regime Barbell

Status: **research-only; not promoted**.

`v48_regime_barbell` combines the immutable causal trend/value sleeve and
Ultimate-RSI mean-reversion sleeve.  It supports the pre-registered policies
`static_80_20`, `static_75_25`, `static_67_33`, `regime`, and
`regime_feedback`.

The regime policy reads the previous completed daily regime only.  The feedback
policy uses a 60-bar EWMA of each sleeve's prior after-cost returns and is capped
at a ten-percentage-point tilt.  A missing regime source raises in strict
research mode and falls back to static 75/25 only in degraded live mode.

Run the controlled workflow with:

```bash
.venv/bin/python tools/feedback_loop_v48.py audit-baselines
.venv/bin/python tools/feedback_loop_v48.py research --cash 1000
```

`freeze` is intentionally blocked unless a policy passes the research gates.
After freezing, `shadow-report` compares the untouched candidate against the
causal trend control without changing either model.

The first implementation smoke did not pass the drawdown gate.  It is evidence
that the promotion controls work, not evidence of an investable edge.
