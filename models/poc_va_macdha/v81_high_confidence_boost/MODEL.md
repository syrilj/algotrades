# v81 high-confidence boost

Research challenger to `v72_dual_sleeve`.

## Contract

- `v72_dual_sleeve` remains the primary side and exit authority.
- `v70_high_confidence_wr` may raise an already-active v72 target to a frozen
  weight floor.
- The precision sleeve cannot create orphan trades, short, reverse, or exceed
  the 50% per-symbol cap.
- `last_high_confidence[code]` identifies the v70-qualified subset.
- `last_confidence=0.90` on that subset is a research target. Historical v70
  win rate was 90.9% in the locked holdout, but holdout `n=11` is thin and does
  not establish a guaranteed 90% probability.

## Selection protocol

The target-weight menu is selected on 2024-08-01 through 2025-08-01 only.
The selected rule is then frozen and evaluated once on 2025-08-01 through
2026-07-11. It is not promoted unless it beats v72 under return, Sharpe,
drawdown, and sample-size gates.

## Frozen result (2026-07-16)

Train-only selection chose `precision_target_weight=0.40`.

| model | window | return | max DD | Sharpe | trades | win rate |
|---|---|---:|---:|---:|---:|---:|
| v81 | holdout | +90.5% | -17.8% | 2.13 | 84 | 65.5% |
| v72 | holdout | +81.6% | -19.6% | 2.20 | 84 | 65.5% |
| v81 | full | +510.8% | -18.0% | 2.88 | 177 | 71.8% |
| v72 | full | +513.1% | -19.4% | 3.08 | 179 | 72.1% |
| v70 precision subset | holdout | +13.9% | -11.9% | 1.19 | 11 | 90.9% |

Verdict: **research only, not promoted**. It improves holdout return and
drawdown, but misses the holdout Sharpe and full-return promotion locks. The
90.9% subset is only 11 holdout trades, so it is not a statistically secure
90% probability claim.

For the 10/11 holdout wins, the approximate 95% Wilson interval is 62.3% to
98.4%. More forward observations are required before treating 90% as calibrated.
