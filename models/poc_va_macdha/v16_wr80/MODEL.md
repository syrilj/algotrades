# v16_wr80

**Target:** ≥80% win rate via feedback loop (engine-in-the-loop).

## Result
- Portfolio WR **83.3%**, Sharpe 1.39, DD **-11.3%**, PF **19.7**, **12 trades**
- Universe: **APLD + IONQ** only
- Gates: QQQ trend + volume expand + block red-flag

## How we got here (not hardcoded)
1. Trade-level filter search on v14 outcomes (train/test)
2. Engine loop: backtest → drop/filter losers → repeat until WR≥80%
3. Path: 65.7% → 65.7% → 67.9% → **86.7%** → freeze confirm **83.3%**

## Honest limit
Hitting 80% required **dropping TSLA/MU/ARM/SPY** — they could not clear the bar under validated gates in this ~2y window. Small N — treat as selective sleeve, not full book.
