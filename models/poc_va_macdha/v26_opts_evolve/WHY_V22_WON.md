# Why v22 beat stock books (and what to keep)

## What “v22” actually is

Not a new price-ML model. Stack:

```
Equity SIDE (v21 POC/VA + MACD-HA specialists)
  → long ATM / near-ATM calls, ~21 DTE
  → size = risk_pct × equity × signal strength (compound)
  → halt ~30% DD / flatten ~45%
  → universe evolved by hunt feedback
```

## Why it beat pure equity (v23/v25 class) for *growth*

| Factor | Stock books | v22 options |
|--------|-------------|-------------|
| Payoff | ~1R–3R stock moves | Option leverage on same timing |
| Selectivity | Many trades, ~65% WR | **Few trades (22), ~82% WR** |
| Universe | Broad + macro | **Hunt-ranked bag** IONQ/AVGO/HOOD/MU |
| Size | Fraction of equity in shares | **10% of equity in premium** (compounds) |
| Failures | Lags SPY in bull | Survives with DD floor |

Hunt synthesis (65 runs): **diversified bags >> solo lottery** on full window risk-adj.  
Solo ranking then **replaced APLD/TSLA with AVGO/HOOD** → **+53% → +60%** on full period.

## What v22 still leaves on the table

1. **Exits only on equity signal flip** — no premium react cut / trail (options playbook).  
2. **Can open several names at once** — dilutes compound path that made 30d moonshots.  
3. **No volume gate** — vol_z / expand was the strongest meta on stock research.  
4. **Fixed risk_pct** — no streak feedback (size up after wins, cut after loss).  
5. **OOS 2022–2024 bag was weak** — need tighter entry quality, not more leverage.

## What we tried on top of v22 (and learned)

| Change | Full-window result vs v22 +59.8% |
|--------|----------------------------------|
| Vol gate + concentrate + under-stop | **Worse** (~+19–39%) — classic over-filter |
| Streak size only | **Worse** (~+49%), higher WR |
| risk_pct 12–15% | **Worse** — fewer contract fills / path change |
| **dte_days 14, risk 10%, else v22** | **BEAT: +64.5%, DD −9.3%, Sharpe 1.40** |

## v26 promoted design

**Keep 100% of v22 DNA** (engine, bag, 10% risk, multi-name, signal exits, DD floors).  
**One structure upgrade:** ATM calls **14 DTE** instead of 21 (more gamma to the stock move, less dead theta wait).

Do **not** stack vanity gates. Improve universe via hunt feedback (as v22 did), not filter piles.
