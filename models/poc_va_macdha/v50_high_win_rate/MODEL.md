# v50_high_win_rate

**Status: PROMOTED high-confidence / high win-rate equity candidate** (2026-07-15).

## Design

- **Teacher:** `v45_ultimate_rsi` mean-reversion (Ultimate RSI red → long, green → flat).
- **Trend:** price > SMA(250), applied **entry-only**.
- **Sizing:** `signal_scale = 0.225` (22.5% target weight).
- **No secondary consensus** in the promoted config (v41 consensus starved trades in prior tests).

## Verified contract

`EQUITY_WINNER_BAG`, `source=local`, `interval=1H`, cash `$1,000`.

| Window | ret | max DD | Sharpe | n | WR | final |
|--------|----:|-------:|-------:|--:|---:|------:|
| Full 2024-08-01 → 2026-07-11 | +108.7% | −19.5% | 1.87 | 52 | **86.5%** | $2,087 |
| Holdout 2025-08-01 → 2026-07-11 | +30.6% | −19.5% | 1.27 | 27 | **77.8%** | $1,306 |

## Integrity

- Local adjusted prices (not unadjusted yfinance vanity).
- Entry-only trend filter (does not force-exit mid-trade on SMA flicker).
- Evolve auditor: WARN only (`below_claim_n` vs PASS_BAR 40); no look-ahead FAIL/BLOCK.
- Successor experiment `v70_high_confidence_wr` raises WR further but thins OOS below auditor floors → research-only.

## Run

```python
import dynamic_model_rank as dmr
from evolve.farm import EQUITY_WINNER_BAG
m = dmr.discover_models(["v50_high_win_rate"])[0]
dmr.run_one(m, mode="daily", codes=EQUITY_WINNER_BAG,
            start="2024-08-01", end="2026-07-11", tag="verify",
            cash=1000, force_1d=False, source="local", interval="1H")
```
