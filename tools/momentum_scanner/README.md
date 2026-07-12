# Momentum Scanner - Quick Reference

## Output Format
```
IONQ.US: 🚀💥 C=0.75 P=0.10 rvol=2.3 ↑0.75
           │   │
           │   └─ Volume surge (rvol > 1.5)
           └─ Squeeze release detected
```

## Signal Interpretation

**Call Score (C):**
- 0.00-0.25: Watch only
- 0.25-0.50: Early setup forming
- 0.50-0.75: Strong momentum setup
- 0.75-1.00: Explosion imminent - enter

**Put Score (P):**
- Inverse of call for downside breakouts

## Current Algorithm

1. **Squeeze Release**: Bollinger contraction → breakout
2. **Volume Surge**: Volume > 1.5x 20-day average
3. **Direction**: 3%+ move on signal day
4. **Score**: Weighted sum (max 0.3 each from vol/squeeze/direction)

## Usage

```bash
# Scan current holdings
python3 tools/momentum_scanner/scan.py

# Add symbols to config.json
# Set alerts on squeeze_release=true AND vol_surge=true
```

## For $1K → $1M Goal

- Enter when C score >= 0.50 (high probability)
- Size 25-50% account per trade
- Target 10x-30x moves (let gamma work)
- Stop: break below VAL or 30% timer