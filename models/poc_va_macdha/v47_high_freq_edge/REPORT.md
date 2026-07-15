# v47_high_freq_edge Report

**Period:** 2024-08-01 → 2026-07-11  
**Universe:** `EQUITY_WINNER_BAG` (`TSLA.US`, `MU.US`, `SPY.US`, `IONQ.US`, `APLD.US`, `XLP.US`, `QQQ.US`)  
**Scale:** $1,000  
**Source:** `local` (adjusted 1H equity data)  
**Tag:** `final`

## Summary

| Metric | Value |
|--------|-------|
| Final value | **$4,065.51** |
| Total return | **306.6%** |
| Annual return | 107.8% |
| Max drawdown | **-21.8%** |
| Sharpe | **1.68** |
| Calmar | 4.94 |
| Sortino | 1.88 |
| Win rate | **55.2%** |
| Profit / loss ratio | 1.29 |
| Profit factor | 1.59 |
| Max consecutive losses | 8 |
| Trade count | **306** |
| Benchmark return | 293.1% |
| Excess return | +13.5% |

## What this model does

`v47_high_freq_edge` is a high-frequency 1H mean-reversion engine:

- **Primary entry:** Ultimate RSI crosses under 30 (`os_value=30`) on the 1H timeframe.
- **Primary exit:** first of
  1. Ultimate RSI crosses over 70 (`ob_value=70`),
  2. ATR(14) trailing stop at `2.5 × ATR` below the highest price since entry,
  3. `max_hold_bars=8` vertical barrier.
- **No trend filter** and **no volume filter** in the tuned config. On this timeframe, the oscillator + ATR stop + max-hold combination is self-contained.
- **Rule-based meta-sizing:** confidence is 1.0 when volume is present (always 1.0 here because `use_volume` is disabled for the tuned run). The model is fully invested per trade.

## Why this is different from the champion

| Model | Return | DD | Sharpe | Trades | Timeframe |
|-------|--------|----|--------|--------|-----------|
| `v39d_confluence` | 357.5% | -13.4% | 2.82 | 135 | 1H / 4H confluence |
| `v45b_ultimate_rsi_stops` | 876.1% | -25.5% | 1.91 | 34 | 4H |
| **v47_high_freq_edge** | **306.6%** | **-21.8%** | **1.68** | **306** | **1H** |

`v47` trades ~9× more than `v45b` and ~2.3× more than `v39d`, while keeping drawdown below the `v45b` level and producing a Sharpe above the `v45b` raw-return variant. It is the best current model for users who explicitly want **high trade count + profit with controlled risk**.

## Tuning journey

1. Initial baseline (`1H`, `os=40`, `ob=60`, `atr=1.2`, `max_hold=12`, trend + volume filters) produced **181 trades, -26.3% return, -46.0% drawdown** — too loose and risky.
2. Removing the filters and moving to 4H (`os=30`, `ob=70`, `atr=2.5`, `max_hold=8`) gave **74 trades, +310.7% return, -31.8% drawdown** — profitable but not enough trades.
3. Dropping the timeframe to **1H** with the same 4H-inspired parameters produced the final result: **306 trades, +306.6% return, -21.8% drawdown**.

The `max_hold_bars` vertical barrier is the key addition over `v45b`: it forces the engine to recycle capital quickly, which is what drives the high trade count while the ATR trailing stop keeps the losers small.

## Limitations / next steps

- **Overfitting risk:** this is a single backtest window. A proper out-of-sample / CPCV test is needed before production sizing.
- **No meta-learner yet:** the confidence is a rule (trend + volume). The candidate ledger can be used to train a secondary XGB model to filter the 1H entries.
- **Regime / correlation:** a market-wide risk-off period may increase consecutive losses. Consider a broad market stop (e.g., SPY 4H < SMA(50)) or HRP allocation across symbols.
- **Take-profit:** `use_tp` is currently disabled. A dynamic take-profit (e.g., `tp_atr_mult` = 2.5–3.0) may further improve profit/loss ratio.

## Recommended verification

```bash
.venv/bin/python - <<'PY'
import sys
from pathlib import Path
ROOT = Path('/Users/syriljacob/Desktop/TradingAlgoWork')
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
import dynamic_model_rank as dmr

codes = ['TSLA.US', 'MU.US', 'SPY.US', 'IONQ.US', 'APLD.US', 'XLP.US', 'QQQ.US']
model = dmr.discover_models(['v47_high_freq_edge'])[0]
row = dmr.run_one(model, mode='daily', codes=codes, start='2024-08-01', end='2026-07-11', tag='verify', cash=1000, force_1d=False, source='local', interval='1H', reuse=False)
print(row)
PY
```
