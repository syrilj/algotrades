# v22_opts_agg — high-risk big-move sleeve

## Idea
You were right that **raising risk + hunting torque** beats the conservative book — full-window end/$1k went from ~$1.6k → **$2157**.

## Spec
- Name: **AVGO** (best of 68 aggressive runs)
- 12% OTM calls, **7 DTE**, **50%** equity premium risk per entry
- Flatten only at ~95% DD (almost no safety net)

## Results (research, BS options)
- $1k → **$2157** (+116%)
- Best **2-week** spike in-sample: **+145.1%** (~2.5×, not 1000×)
- Across all 68 aggressive runs: **0** hit 10× / 100× / 1000× on the full window

## Reality check on “2 weeks → $1M”
$1k→$1M needs **10 doubles in a row** (2^10=1024). Best 14-day spike here was ~2.5× once — not ten perfect doubles. Possible in theory on a lottery path; **not what the backtests produced**.

## Safer aggressive cousin
`agg_ionq__week_atm20`: +110%, DD −13%, 20% risk / 14 DTE ATM.
