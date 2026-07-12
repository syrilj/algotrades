# Options hunt synthesis

Jobs: 65 · OK: 65 · FAIL: 0

## Best experiments (by total return)

| rank | name | ret | DD | Sharpe | n | end/$1k | yrs→$1M |
|-----:|------|----:|---:|-------:|--:|--------:|--------:|
| 1 | `bag_v20winners__atm10_21` | 53.3% | -10.7% | 1.40 | 22 | $1533 | 31.2 |
| 2 | `bag_v20winners__otm8_14` | 46.9% | -6.3% | 1.57 | 22 | $1469 | 34.6 |
| 3 | `bag_v20winners__atm5_30` | 40.1% | -10.8% | 1.38 | 24 | $1401 | 39.6 |
| 4 | `solo_avgo__atm10_21` | 24.7% | -15.2% | 0.63 | 10 | $1247 | 60.4 |
| 5 | `solo_ionq__atm5_30` | 23.7% | -12.4% | 0.99 | 10 | $1237 | 62.7 |
| 6 | `solo_ionq__atm10_21` | 20.9% | -14.7% | 0.86 | 10 | $1209 | 70.3 |
| 7 | `solo_hood__atm10_21` | 19.2% | -10.4% | 0.64 | 10 | $1192 | 75.8 |
| 8 | `solo_gme__atm10_21` | 17.0% | -14.0% | 0.61 | 10 | $1170 | 84.8 |
| 9 | `solo_rklb__atm5_30` | 14.2% | -7.0% | 0.92 | 22 | $1142 | 100.3 |
| 10 | `solo_mu__atm10_21` | 14.0% | -6.8% | 0.60 | 10 | $1140 | 101.9 |
| 11 | `lotto_ionq__lotto15_10` | 13.7% | -6.9% | 0.73 | 10 | $1137 | 103.8 |
| 12 | `solo_avgo__atm5_30` | 12.7% | -9.2% | 0.59 | 10 | $1127 | 111.5 |
| 13 | `solo_tsla__atm10_21` | 12.3% | -7.5% | 0.79 | 12 | $1123 | 114.7 |
| 14 | `solo_coin__atm10_21` | 12.1% | -11.3% | 0.52 | 8 | $1121 | 116.4 |
| 15 | `bag_semi__atm10_21` | 11.4% | -5.2% | 0.66 | 12 | $1114 | 123.5 |

## Best underlyings (avg across solo styles)

- **IONQ.US**: avg 19.4% · best 23.7% · (3 styles)
- **AVGO.US**: avg 18.7% · best 24.7% · (2 styles)
- **HOOD.US**: avg 14.5% · best 19.2% · (2 styles)
- **GME.US**: avg 10.9% · best 17.0% · (3 styles)
- **COIN.US**: avg 9.6% · best 12.1% · (2 styles)
- **MU.US**: avg 9.2% · best 14.0% · (2 styles)
- **TSLA.US**: avg 9.1% · best 12.3% · (2 styles)
- **RKLB.US**: avg 7.8% · best 14.2% · (2 styles)
- **ARM.US**: avg 5.9% · best 6.5% · (2 styles)
- **APLD.US**: avg 5.0% · best 7.6% · (3 styles)

## Live candidate seed

- Experiment: `bag_v20winners__atm10_21`
- Codes: ['MU.US', 'APLD.US', 'IONQ.US', 'TSLA.US']
- Style: `atm10_21`
- End per $1k: **$1533**
- Years to $1M at this CAGR: **31.18432806081415**

## Feedback loop (post-hunt)
Evolved bag **IONQ+AVGO+HOOD+MU** @ atm10_21 → **59.8%** (end/$1k **$1598**), DD -11.2%.
Promoted to `models/poc_va_macdha/v22_opts_live/` for live.
