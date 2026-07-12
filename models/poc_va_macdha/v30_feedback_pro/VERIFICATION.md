# v30_feedback_pro — VERIFICATION REPORT (FAILED)

## Real Backtest Results (2026-07-12)

| Metric | v28_baseline | v30_result | v32_winner |
|--------|-------------|------------|------------|
| Total Return | +74.5% | +84.3% | +108.3% |
| Sharpe | 1.17 | 1.25 | **1.49** |
| Max DD | -15.5% | -13.3% | -12.5% |
| Trade Count | 24 | 36 | 34 |
| Win Rate | 75% | 67% | 71% |

## Root Cause: Hard Filters Kill Performance

v30 used **hard entry filters** (skip if no volume surge, skip if below 200 SMA). This reduced the win rate significantly while only marginally improving DD.

## Correct Approach (v32): Soft Sizing

```python
# WRONG - hard block (v30)
if spot < sma200: continue  # Hard block

# RIGHT - soft sizing (v32)
if structure_good: size_mult = 1.15
else: size_mult = 0.55  # Never zero, never block
```

See `/models/poc_va_macdha/v32_soft_react_opts/signal_engine.py` for the working implementation.

## Recommendation

**DO NOT USE v30** - Use **v32_soft_react_opts** instead which achieves:
- +108.3% return (vs v30 +84.3%)
- Sharpe 1.49 (vs v30 1.25)
- 3/3 walk-forward wins vs v28