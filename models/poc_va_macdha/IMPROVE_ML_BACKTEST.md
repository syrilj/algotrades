# Harder backtests + XGBoost filter (win-rate path)

## What you have today (not ML)

`v2_vwap` is a **rule stack**, not a trained model:

1. Resample to **2H**; HTF trend = **4H St.MACD Heikin-Ashi green**
2. Prior lookback **volume profile** → POC / VAL / VAH
3. Long only if: `close >= POC` AND inside `[VAL, VAH]` AND HTF green
4. Extra gates (v2): swing-anchored VWAP uptrend, price above VWAP, volume ≥ SMA
5. Exit when HTF not green, close < VWAP, or local HA red while HTF red

Backtest harness: `config.json` → `backtest.runner` loads `runs/.../code/signal_engine.py`.

### Current v2 reality (portfolio)

- Win rate ~44%, profit factor ~0.93, total return ~-13%, max DD ~-62%
- Only ~2y window (`2024-08` → `2026-07`), 6 names, ~131 trades — too short / too few for stable ML

---

## Harder / longer backtests (do this first)

Edit `config.json` (and keep a frozen copy under each model version):

| Knob | Soft (now) | Harder |
|------|------------|--------|
| `start_date` | 2024-08-01 | **2018-01-01** (or 2020-01-01) |
| `codes` | 6 mega-vol names | Add liquid beta: QQQ, IWM, AAPL, NVDA, META; drop or isolate IONQ/APLD in a separate bucket |
| Validation | Full-sample tune | **Walk-forward by quarter** (train Q, test Q+1; never retune on test) |
| Costs | 0.001 | Keep + optional slippage stress (2× commission) |
| Metrics to beat | Win rate alone | Win rate **and** profit factor > 1.2, max DD < 25%, Sharpe > 0.5 OOS |

Prompt baseline to beat (SPY, longer window): Sharpe 0.64, +70% return, DD -21%, WR 68%.

---

## LSE XGBoost takeaways → your stack

From [LSE XGBoost](https://londonstrategicedge.com/machine-learning/algorithms/xgboost): XGBoost is strong on **tabular alpha**, with focus on **learning rate / max depth / regularisation** and **SHAP feature importance**.

**Do not replace the whole strategy with raw XGB on close prices.** Use it as a **trade filter / ranker** on candidates your rules already propose.

### Label (no lookahead)

For each rule-generated long candidate at bar `t`:

- `y = 1` if forward return to exit (or +N bars) > costs + buffer
- `y = 0` otherwise

### Features (from existing engine state)

- Distances: `(close-POC)/ATR`, `(close-VAL)/ATR`, `(close-VWAP)/ATR`
- HTF HA green age, local HA color, MACD hist slope
- Volume expand ratio, VWAP uptrend flag
- Squeeze / vol-div flags (from `poc_va_train` helpers)
- Symbol one-hots or market regime (SPY trend)

### Model discipline

- `learning_rate` low (0.01–0.05), `max_depth` shallow (3–5), L1/L2 reg on
- Time-series CV / walk-forward only (no random k-fold)
- SHAP: keep top features; drop noisy ones
- Signal = rule entry **and** `P(win) >= threshold` (tune threshold on validation only)

### Sizing (v6 softconf direction)

Map `P(win)` → position scale `{0.25, 0.5, 1.0}` instead of binary 0/1.

---

## Implementation order

1. **Longer OOS config** — copy `v2_vwap` → `v2_vwap_long` with `start_date=2018-01-01`, same rules; record metrics
2. **Candidate logger** — dump feature rows + forward labels from backtest bars
3. **`ml_filter/train_xgb.py`** — walk-forward XGB + SHAP report
4. **`v7_xgb` SignalEngine** — load frozen booster; gate entries by probability
5. Compare OOS win rate / PF / DD vs v2; only promote if OOS improves

## Honest constraint

Raising win rate by stacking more AND filters often **cuts trades and still loses** if edge is weak. Prefer: longer history → measure true edge → XGB filter on probability → size by confidence. Win rate without profit factor / DD is a vanity metric.
