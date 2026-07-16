# v72_trump_risk_hard

Trump second-term live-oriented overlay: **v39d_confluence** teacher + **hard stand-aside** when composite swing-drawdown risk is elevated.

## Sensors (causal)
- SPY drawdown-from-peak stress
- SPY realized-vol spike vs expanding median (lagged returns)
- SPY below SMA50
- QQQ drawdown stress

## Policy
`risk_score >= 0.55` → size multiplier `0` (flat). Else teacher target unchanged.

## Sibling
`v72b_trump_risk_soft` — v39b teacher + continuous soft scale + optional crypto-corridor (COIN/MSTR).
