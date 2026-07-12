# v36_sharpe_meta

**Goal:** Grow a **$1,000** account with the best **live Sharpe** recipe.

## Loop
1. Re-evaluate contender models on $1k options bag  
2. Mine features (IC × stability, de-correlated)  
3. Softmax-reward models by Sharpe (+ light return bonus)  
4. Walk-forward MLP meta filter on selected features  
5. Primary engine = highest reward weight; soft-size only  

## Parent
`v15_meta_xgb`

## Selected features
- `atr_14`
- `range`
- `atr_pct`
- `room_pct`
- `macd_hist`
- `ret_5d`

## Do not
- Hard-block entries (v29/v31 fail mode)
- Trade MU ATM on $1k
- Optimize for win-rate vanity

See `runs/poc_va_feature_evolve_1k/EVOLVE_REPORT.md` and `META_ENSEMBLE.json`.
