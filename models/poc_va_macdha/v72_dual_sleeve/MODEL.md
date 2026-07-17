# v72_dual_sleeve

**Status: PROMOTED live combined equity book** (2026-07-15).

Hierarchical merge of high-WR sniper + return champion — **not** signal averaging.

## Design

| Sleeve | Model | Role |
|--------|-------|------|
| Sniper | `v71_live_confidence` | High win-rate mean-rev + confidence sizing |
| Core | `v39d_confluence` | Return / Sharpe champion |

**Merge rule:**

1. Sniper long → take sniper weight.
2. Else core long → take `0.85 ×` core weight.
3. Both long → sniper + `0.35 ×` scaled core, **capped at 50%** target weight.
4. Flat → 0.

Live: `last_confidence[code]`, `last_sleeve[code]` (0/1/2/3 = flat/sniper/core/both).

## Verified contract

`EQUITY_WINNER_BAG`, `source=local`, `interval=1H`, cash `$1,000`.

| Window | ret | max DD | Sharpe | n | WR | final |
|--------|----:|-------:|-------:|--:|---:|------:|
| Train 2024-08-01 → 2025-08-01 | +216.6% | −11.4% | 3.60 | 93 | 73.1% | $3,166 |
| **Holdout 2025-08-01 → 2026-07-11** | **+81.6%** | −19.6% | **2.20** | 84 | 65.5% | $1,816 |
| Full 2024-08-01 → 2026-07-11 | **+513.1%** | −19.4% | **3.08** | 179 | 72.1% | **$6,131** |

## Vs peers (same contract)

| Model | full ret | full Sharpe | full WR | OOS ret | OOS Sharpe |
|-------|---------:|------------:|--------:|--------:|-----------:|
| **v72_dual_sleeve** | **+513%** | **3.08** | 72% | **+82%** | **2.20** |
| v39d_confluence | +357% | 2.82 | 67% | +50% | 2.13 |
| v71_live_confidence | +114% | 1.72 | 86% | +31% | 1.17 |
| v50_high_win_rate | +109% | 1.87 | 87% | +31% | 1.27 |

## Trade-offs

- **Better** total return and Sharpe than pure v39d on this bag/window.
- **Worse** max drawdown (~−19% vs v39d ~−13%). Size for the deeper DD in live risk.
- WR sits between sniper (86%) and core (67%) — as expected for a dual book.

## Integrity

- Teachers frozen (`v71` sizeup_q1, shipped `v39d`).
- Hierarchical merge pre-registered; no post-holdout retune.
- Artifacts: `runs/v72_dual_sleeve/COMPARE.json`, `STATE.json`.

## Run

```python
import dynamic_model_rank as dmr
from evolve.farm import EQUITY_WINNER_BAG
m = dmr.discover_models(["v72_dual_sleeve"])[0]
dmr.run_one(m, mode="daily", codes=EQUITY_WINNER_BAG,
            start="2024-08-01", end="2026-07-11", tag="verify",
            cash=1000, force_1d=False, source="local", interval="1H")
```

Desk:

```bash
.venv/bin/python tools/trade_desk.py TSLA --model v72_dual_sleeve
.venv/bin/python tools/live_plan.py --symbol TSLA --account 1000 --model v72_dual_sleeve --json
```
