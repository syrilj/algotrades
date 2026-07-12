# v34_momo_detector — Catch Momentum Explosions Early

**Goal:** For $1K accounts - catch IONQ/AVGO-style 10x-30x momentum explosions

## Key Setup Pattern

1. **Squeeze Release** - Bollinger contraction → breakout imminent
2. **Volume Surge** - rvol >= 1.5x SMA20 on breakout bar
3. **POC/VAH Break** - Price clears value area overhead
4. **HTF HA Green** - Momentum confirmation on 1D/4H

## Entry Conditions

```
squeeze_release AND (rvol >= 1.5 OR price-up-on-volume-expand) AND poc_hold AND htf_green
```

## Exit Strategy

- Target 100% move (let gamma do work)
- Stop: break below VAL or 30% trailing
- Max hold: 5 trading days (momentum fades)

## Position Sizing

- Risk: 25% of account per trade ($250 on $1K)
- Minimum contracts: 1 (micro sizing for small account)
- Let winners run 10-50x with tight stop

## Universe

High-beta tech names that can explode:
- IONQ, AVGO, NVDA, AMD, TSLA, MSTR, HOOD