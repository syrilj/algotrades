# v20_profit_risk — what was traded

Universe: **TSLA, ARM, MU, SPY, IONQ, APLD** (no MSTR).

Start **$1,000,000** → end **~$3,587,037** (+258.7%). Equity backtest **already compounds** (share size grows after winners).

## PnL by name

| code    |   exits |       total_pnl |   avg_ret_pct |   win_rate |
|:--------|--------:|----------------:|--------------:|-----------:|
| MU.US   |      89 |      1.1735e+06 |      0.60236  |   0.573034 |
| APLD.US |      28 | 685892          |      3.24607  |   0.785714 |
| IONQ.US |      31 | 463716          |      2.88677  |   0.645161 |
| TSLA.US |      37 | 170201          |      0.358378 |   0.621622 |
| ARM.US  |      30 |  82004.6        |     -0.366    |   0.533333 |
| SPY.US  |       8 |  11718          |      0.06375  |   0.625    |

## TSLA sample (compounding qty)

| timestamp   | code    | side   |   price |     qty | reason   |      pnl |   holding_days |   return_pct |
|:------------|:--------|:-------|--------:|--------:|:---------|---------:|---------------:|-------------:|
| 2024-08-14  | TSLA.US | buy    | 200.81  | 3089.96 | signal   |     0    |              0 |         0    |
| 2024-08-15  | TSLA.US | sell   | 213.873 | 3089.96 | signal   | 40363    |              1 |         6.5  |
| 2024-08-16  | TSLA.US | buy    | 216.565 | 4774.81 | signal   |     0    |              0 |         0    |
| 2024-08-19  | TSLA.US | sell   | 221.773 | 4774.81 | signal   | 24865.5  |              2 |         2.4  |
| 2024-08-19  | TSLA.US | buy    | 220.96  | 4820.9  | signal   |     0    |              0 |         0    |
| 2024-08-19  | TSLA.US | sell   | 222.769 | 4820.9  | signal   |  8716.83 |              0 |         0.82 |
| 2024-08-20  | TSLA.US | buy    | 221.171 | 4844.11 | signal   |     0    |              0 |         0    |
| 2024-08-20  | TSLA.US | sell   | 221.439 | 4844.11 | signal   |  1302.06 |              0 |         0.12 |
| 2024-09-06  | TSLA.US | buy    | 216.978 | 3083.24 | signal   |     0    |              0 |         0    |
| 2024-09-09  | TSLA.US | sell   | 218.271 | 3083.24 | signal   |  3984.73 |              2 |         0.6  |
| 2024-09-18  | TSLA.US | buy    | 228.344 | 2412.18 | signal   |     0    |              0 |         0    |
| 2024-09-23  | TSLA.US | sell   | 249.135 | 2412.18 | signal   | 50152.2  |              5 |         9.11 |
