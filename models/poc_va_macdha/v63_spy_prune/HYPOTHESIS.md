# v63_spy_prune

**Diagnosis-driven beat of v39d_confluence**

## Evidence (champion candidate ledger, full hunt)
- SPY.US: n=26 candidates, **31% WR**, ~0 expectancy; trades sum PnL ~$66 vs MU/APLD ~$1.1k each
- Edge carriers: MU, IONQ, APLD (and TSLA secondary)

## Change
- `TRADE_DROP = {"ARM.US", "SPY.US"}` (was ARM only)
- No new features, no stop changes, no meta retrain

## Results ($1k, local 1H, EQUITY_WINNER_BAG)
| Phase | Model | ret | dd | sharpe | n | wr |
|-------|-------|-----|----|--------|---|----|
| Hunt | v39d | 357.5% | -13.4% | 2.82 | 135 | 67% |
| Hunt | v63 | 373.7% | -13.1% | 2.78 | 117 | 73% |
| Lockbox | v39d | 50.0% | -12.3% | 2.13 | 65 | 62% |
| Lockbox | v63 | **61.0%** | **-11.9%** | **2.21** | 55 | 69% |

## Promote
Lockbox multi-lock vs frozen v39d: **PASS** (ret↑, sharpe↑, dd not worse).
