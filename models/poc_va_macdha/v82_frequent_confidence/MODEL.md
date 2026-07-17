# v82 Frequent Confidence

Research model for more frequent high-quality **1H swing** entries.

- Liquid core (`SPY`, `QQQ`, `XLP`, `MU`, `NVDA`, `TSLA`) uses the balanced
  `v71_live_confidence` sleeve.
- Volatile satellites use the strict `v70_high_confidence_wr` quality gate.
- Bond ETFs (`HYG`, `LQD`) are excluded because this equity mean-reversion
  teacher is not designed for their return process.
- Per-symbol target weight is capped at 35%.

`last_confidence` is an uncalibrated ordinal ranking score. It must not be
displayed as a win probability. `last_tier` is 1 for balanced-core exposure and
2 for strict satellite exposure; `last_strict_tier` is the explicit boolean
strict-gate flag. “Strict” describes the entry filter, not a promised win rate.

This routing was designed after inspecting the historical window. Results are
retrospective research, not pristine OOS evidence. Do not promote it until a
new forward paper-trading window confirms trade frequency, win rate, drawdown,
and confidence calibration.
