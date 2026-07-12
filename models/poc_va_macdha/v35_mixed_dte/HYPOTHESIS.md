# v35_mixed_dte — Current Market Setup Identifier

## Mixed DTE Strategy

### LEAPS (30-60 DTE) - For Accumulation Patterns

**When to use:**
- Volume surge with narrow range for 10+ bars (accumulation)
- Price consolidating above 200 SMA
- Volatility percentile < 50%

**Setup:**
- Enter 30-60 DTE call when volume > 2x SMA AND price > POC
- Target 3-5x (more realistic for LEAPS)
- Size: 50-70% account (less theta pressure)

### Short-dated (7-14 DTE) - For Momentum Breakouts

**When to use:**
- Squeeze release pattern
- Volume surge > 1.5x SMA20
- Price breaking above VAH/POC

**Setup:**
- Enter 7-14 DTE call at breakout
- Target 10-50x (gamma explosion)
- Size: 20-30% account (theta decay risk)

## Current Market Screen

Check these conditions on daily charts:

| Symbol | Volatility | VWAP Regime | Signal Bias |
|--------|------------|-------------|-------------|
| IONQ | High (use 7DTE) | Watch for squeeze release | Momentum plays |
| AVGO | Medium | Above VWAP + volume | Growth continuation |
| NVDA | High | Choppy | Wait for clean break |
| TSLA | Extreme | Volatile | Either direction |
| MU | Traditional | Mean-reversion | Fade extremes |

## Implementation

```python
# In signal_engine.py:
# Check for squeeze_release AND rvol > 1.5 → 7DTE aggressive
# Check for vol_percentile < 0.5 AND poc_hold → 14-21DTE
# Check for vol_percentile > 0.75 → 7DTE or skip
```

## Risk Management

- Never lose more than 50% of account in one setup
- After 2 consecutive losers: reduce size to 10%
- After 2 consecutive winners: increase size to 40%
- Max 3 concurrent positions