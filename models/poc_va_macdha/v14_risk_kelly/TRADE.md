# v14_risk_kelly — Tradeable model playbook

## Why this version
v12 had strong returns but **no hard risk layer** (max DD ~−39%).  
v14 keeps v12 per-symbol entries and adds LSE risk rules:

1. **Half-Kelly / confidence sizing** — big size only on high-confidence setups; shrink high-vol names ([Position Sizing](https://londonstrategicedge.com/machine-learning/risk-management/position-sizing/))
2. **Cut losers fast** — hard stop at `entry − 1.5×ATR`
3. **Let winners run** — after `+1×ATR` profit, trail `peak − 2.5×ATR`; ignore soft HTF flicker while armed
4. **Drawdown awareness** — smaller bets + stops → shallower DD ([Drawdown Analysis](https://londonstrategicedge.com/machine-learning/risk-management/drawdown-analysis/))

## Backtest (same window as v12: 2024-08 → 2026-07, 1H)

| Metric | v12 | **v14_risk_kelly** |
|--------|-----|--------------------|
| Total return | +315% | +252% |
| Sharpe | 1.66 | **1.72** |
| Win rate | 62.7% | 61.1% |
| Profit factor | 1.65 | **1.79** |
| Max drawdown | −39% | **−24%** |
| Calmar | ~0.8 | **3.88** |
| Trades | 201 | 221 |

Slightly less raw return, **much better risk-adjusted** — this is the version to trade.

## Paths
- Model: `models/poc_va_macdha/v14_risk_kelly/`
- Live/backtest run: `runs/poc_va_risk/`
- Engine: `runs/poc_va_risk/code/signal_engine.py`

## How to backtest
```bash
cd /Users/syriljacob/Desktop/TradingAlgoWork
.venv/bin/python3 -c "from pathlib import Path; from backtest.runner import main; main(Path('runs/poc_va_risk').resolve())"
```

## Live trading rules (manual / Pine later)
1. **Entry** — only when symbol’s routed gates fire AND confidence ≥ 0.55  
   Confidence = mean of: POC hold, in VA, HTF HA green, VWAP up, above VWAP, vol confirm/healthy pull, not red-flag, mom>0, squeeze off/release
2. **Size (account % of that sleeve)**  
   - conf 0.55–0.65 → **35%** sleeve  
   - conf 0.65–0.78 → **65%** sleeve  
   - conf ≥ 0.78 → **100%** sleeve  
   Then × vol scale: `clip(median_atr%/atr%, 0.4, 1.25)` (high vol → smaller)
3. **Stop** — hard exit if close ≤ entry − 1.5 ATR(14)
4. **Trail** — once peak ≥ entry + 1.0 ATR, exit if close ≤ peak − 2.5 ATR
5. **Soft exits** (HTF fail / below VWAP / etc.) — only **before** trail is armed; after armed, only stop/trail (+ red-flag emergency)

## Risk caps (account level — do this yourself)
- Risk **≤ 1%** of total equity to the ATR stop on any single name (fixed fractional; LSE)
- Prefer **half-Kelly**, never full Kelly
- Optional: pause new entries if portfolio DD from peak ≥ **10%**

## Tunables (in `_ROUTING` per symbol)
`stop_atr`, `trail_atr`, `arm_trail_atr`, `kelly_fraction`, `min_confidence`

## Honest limits
- Yahoo 1H history is short (~2y) — treat metrics as research, not a guarantee
- Still long-only; no short book / no portfolio DD kill-switch inside the engine yet
- Excess vs buy&hold still negative on this mega-vol universe — edge is **risk-adjusted**, not alpha vs SPY-on-steroids names
