# v20_profit_risk — Draft playbook (not backtested yet)

## Goal
Maximize **ending equity** (v12 DNA) while **capping portfolio drawdown** (LSE risk layer beyond v14).

| Anchor | End $ / $1k | Return | Max DD | Sharpe |
|--------|-------------|--------|--------|--------|
| v12_regime_router | ~$4,153 | +315% | −39% | 1.66 |
| v14_risk_kelly | ~$3,524 | +252% | −24% | 1.72 |
| v15_meta_xgb (WINNER) | ~$2,305 | +131% | −13% | 2.13 |
| **v20 target** | **≥ v14** | **≥ +250%** | **≤ −18%** | **≥ 1.72** |

## LSE techniques mapped in

| LSE theme | Implementation |
|-----------|----------------|
| Position sizing / Kelly | Half-Kelly conf buckets × vol scale; never full Kelly |
| Fixed fractional risk | Size to **1% equity** at `1.5×ATR` stop |
| Cut losers fast | Hard ATR stop |
| Let winners run | Trail after +1 ATR arm |
| Drawdown analysis | Soft size cut at 5% DD; halt entries at 10%; flatten research-stop at 15% |

Refs: [Risk Management hub](https://londonstrategicedge.com/machine-learning/risk-management/) · [Position sizing](https://londonstrategicedge.com/machine-learning/risk-management/position-sizing/) · [Drawdown analysis](https://londonstrategicedge.com/machine-learning/risk-management/drawdown-analysis/)

## Stack (planned)

```
v12 ROUTING entries
  → confidence ≥ 0.55
  → size = risk_pct equity / stop_distance
  → × half-Kelly bucket × vol_scale
  → × portfolio_dd_mult(d)
  → v14 stop / trail / soft-exit rules
```

## Status
**Backtested** 2026-07-11. Engine + `runs/poc_va_v20_profit_risk` wired.

| Metric | v14 | **v20** | v15 |
|--------|-----|---------|-----|
| Return | +252% | **+259%** | +131% |
| End/$1k | $3,524 | **$3,587** | $2,305 |
| Max DD | −24% | **−23%** | −13% |
| Sharpe | 1.72 | **1.82** | 2.13 |
| PF | 1.79 | **1.86** | 2.68 |

Pass: return/Sharpe/PF/trades. Fail: DD ≤18% (got −23%). Beats v14; not v15 on DD/Sharpe.

```bash
.venv/bin/python3 -c "from pathlib import Path; from backtest.runner import main; main(Path('runs/poc_va_v20_profit_risk').resolve())"
```
