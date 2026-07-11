# Anti-overfit protocol (training / feedback loops)

**User requirement:** Models must not only look good on data they already “know.” Freeze rules, then test on later / different date ranges.

## Hard rules

1. **Chronological splits only** — never random k-fold on time series.
2. **Tune on train only** — filter/threshold choice uses pre-lock data exclusively.
3. **Holdout after lock** — score frozen rules on `entry_ts >= lock_date` with **no retune**.
4. **Multiple lock dates** — if it only works for one lucky cut, treat as fragile.
5. **Calendar stability** — same frozen mask across halves/quarters; late slices must not die.
6. **Vanity WR insufficient** — PASS_BAR still requires PF / Sharpe / DD / min trades / expectancy.
7. **Forbidden** (from `PASS_BAR.json`): random k-fold, predict-next-close as primary, tune threshold on test, retrain-on-full-sample to “fix” an OOS fail.

## Fail flags (stress harness)

Script: `runs/poc_va_antioverfit/stress_holdout_ranges.py`

- Holdout WR drops **>15pp** vs pre-lock train WR  
- Pre-lock expectancy > 0 but holdout expectancy ≤ 0  
- Holdout n < 5 → **THIN** (no claim), not a pass  

## What “good” looks like

- Several lock dates → **PASS** (or honest THIN on sniper sleeves)  
- Late calendar quarters still positive expectancy under frozen gates  
- Engine re-run on an alternate `start_date`/`end_date` still clears PASS_BAR for hard claims  

## Small-cap note

Sleeve A (APLD/IONQ) will often be **THIN** on holdouts — that is capacity, not proof of overfit by itself. Still require post-lock expectancy not to flip negative when n is adequate.
