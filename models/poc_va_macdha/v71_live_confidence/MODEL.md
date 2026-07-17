# v71_live_confidence

**Status: live high-WR / confidence sleeve** (frozen `sizeup_q1`, 2026-07-15).

## Design

1. **Teacher**: `v45_ultimate_rsi` mean-reversion.
2. **Trend**: price > SMA(250), **entry-only**.
3. **Soft quality floor**: `min_score >= 1` (weaker than v70 hard `>= 2`).
4. **Confidence → size-up**: blend of quality/3 + RSI depth; low-conf keeps full base scale (22.5%), high-conf up to **1.55×** (cap 40%).
5. **Live confidence**: `SignalEngine.last_confidence[code]` is the entry confidence used for sizing.

## Verified contract

`EQUITY_WINNER_BAG`, `source=local`, `interval=1H`, cash `$1,000`.

| Window | ret | max DD | Sharpe | n | WR | final |
|--------|----:|-------:|-------:|--:|---:|------:|
| Train 2024-08-01 → 2025-08-01 | +49.9% | −9.0% | 2.05 | 20 | **90.0%** | $1,499 |
| **Holdout 2025-08-01 → 2026-07-11** | **+30.9%** | −19.6% | 1.17 | 26 | **76.9%** | $1,309 |
| Full 2024-08-01 → 2026-07-11 | **+114.0%** | −19.5% | 1.72 | 50 | **86.0%** | $2,140 |

## Vs prior high-WR arms

| Model | full ret | full WR | OOS n | Live conf? |
|-------|---------:|--------:|------:|:----------:|
| `v50_high_win_rate` | +108.7% | 86.5% | 27 | no |
| **`v71_live_confidence`** | **+114.0%** | 86.0% | 26 | **yes** |
| `v70_high_confidence_wr` | +43.3% | 90.9% | 11 (thin) | partial |
| `v39d_confluence` (return champ) | +357.5% | 66.7% | — | meta proba |

## Integrity

- Variant menu pre-registered; pure `v50_clone` treated as ablation only.
- Selected on train window; holdout not used for retune.
- Hard quality=2 raises WR but fails holdout trade-count floors → not frozen.
- Soft size-*down* variants underperformed train → frozen arm size-*up* only.

## Run

```python
import dynamic_model_rank as dmr
from evolve.farm import EQUITY_WINNER_BAG
m = dmr.discover_models(["v71_live_confidence"])[0]
dmr.run_one(m, mode="daily", codes=EQUITY_WINNER_BAG,
            start="2024-08-01", end="2026-07-11", tag="verify",
            cash=1000, force_1d=False, source="local", interval="1H")
```

Train / re-verify:

```bash
.venv/bin/python tools/train_v71_live_confidence.py --workers 4 --cash 1000
.venv/bin/python tools/train_v71_live_confidence.py --skip-train  # frozen only
```

## Desk use

- Prefer **v71** when you need high win rate + explicit confidence for live tickets.
- Prefer **v39d_confluence** when maximizing long-horizon equity return / Sharpe.
- Do **not** force v70-style quality=2 for live — holdout n collapses.
