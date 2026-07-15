# v44_absorption

**OHLCV-safe order-flow / absorption / volume-cluster overlay on `v39d_confluence`.**

Adds an `order_flow_state` sensor to the v39d_confluence stack:
- candle-delta proxy for LTF CVD
- wick absorption volume
- volume / delta percentile clusters (small / medium / whale)
- composite flow score (imbalance + CVD bias + absorption bias + last cluster direction)

The four scalar features (`flow_score`, `cvd_bias`, `absorption_bias`, `imbalance`) are fed into the XGB meta classifier. Ablation showed the order-flow composite should not boost `adj_proba` directly; it is used as a feature only.

## Results

Reconciled on `source=local` 1H WINNER bag (2024-08-01 → 2026-07-11, $1,000):

- `v44_absorption`: **+262.7% return**, **-17.8% max DD**, **Sharpe 2.24**, **158 trades**, **final $3,627**
- `v39b_live_adapt`: **+309.7% return**, **-13.1% max DD**, **Sharpe 2.70**, **141 trades**, **final $4,097**
- `v39d_confluence`: **+357.5% return**, **-13.4% max DD**, **Sharpe 2.82**, **135 trades**, **final $4,575**

`v44_absorption` does **not** beat either parent on return, Sharpe or drawdown. It is retained as a research artifact.

## Desk

```bash
.venv/bin/python tools/train_v44_meta.py --seed --retrain
```

## Note

The original Pine indicator uses lower-timeframe bid/ask delta and true absorption side. This port is lossy because the repository only has OHLCV bar data. The `imbalance` and `cvd_bias` calculations are intentionally computed on different lookbacks so they are not identical.
