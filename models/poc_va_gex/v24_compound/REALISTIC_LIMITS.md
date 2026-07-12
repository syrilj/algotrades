# v24_compound realistic limits

## What changed

The `SignalEngine.generate_day` now receives the live `cash`/`portfolio_value`/`positions`
state from the options backtest engine, so sizing compounds correctly on the actual
account. It is a single-position engine: it picks the strongest v21 signal each day
(breaking ties by the order the v21 equity engine returns codes), re-enters the same
code on a later day if the signal is still positive and it was not already opened, and
uses `risk_pct` of cash scaled by the raw signal strength.

## Key results

| period | risk_pct | final | total return | trades | win rate |
|---|---|---|---|---|---|
| 2024-08-01 -> 2026-07-11 | 0.5 | $198,811 | 18.88x | 54 | 59.3% |
| 2024-08-01 -> 2024-10-31 | 1.0 | $476,601 | 46.66x | 8 | 100% |
| 2024-08-01 -> 2024-10-23 | 1.0 | $355,307 | 34.53x | 9 | 100% |
| MSTR/TSLA 2024-08-01 -> 2026-07-11 | 0.5 | $11,505 | 1.15x | 26 | 30.8% |

## Why the $1M / 30-day target is not reached

The `v24_compound_feedback.py` research script reaches $1M in a few rolling windows,
but it is a theoretical ledger that applies the full `cash` balance to every new entry
inside a 30-day window, ignoring the fact that capital is tied up while an option
position is open. The real `options_portfolio` engine only has the available `cash` to
deploy, and a single position can only capture one move at a time. The strongest
realistic consecutive chain in the data is roughly `IONQ Sep-25` (2.9x), `IONQ Oct-01`
(1.7x), `IONQ Oct-10` (6.4x) which compounds to about 30-50x on the starting capital,
producing ~$300-475k in the best window. That is the realistic ceiling unless the
trading model can predict multiple independent, non-overlapping 10x moves inside 30
days.

## Recommendation

The realistic target is no longer $1M in 30 days. Use `risk_pct=0.5` on the IONQ/AVGO/HOOD/MU
universe for a robust ~19x full-period return, or accept the much higher variance of
`risk_pct=1.0` for the best windows. MSTR/TSLA is not a better vehicle for this strategy.
