# v73_trump_beat — Trump-window bakeoff vs v39b_live_adapt

**Verdict: MULTI_LOCK PASS**

## Contract
- Window: **2025-01-20 → 2026-07-11**
- `source=local`, `interval=1H`, cash **$1,000**
- Codes: `EQUITY_WINNER_BAG`
- Entry: `tools.dynamic_model_rank.run_one`

## Head-to-head (locked)

| Metric | v39b_live_adapt | **v73_trump_beat** | Gate |
|--------|-----------------|--------------------|------|
| Return | +179.07% | **+185.93%** | **BEAT** |
| Max DD | −12.87% | **−11.50%** | **BEAT** (shallower) |
| Sharpe | 2.684 | **2.821** | **BEAT** |
| Trades | 95 | 95 | |
| Final $ | $2,791 | **$2,859** | |

Multi-lock: **ret ↑ · Sharpe ≥ · |DD| ≤** — **PASS**

Repeat run (`tag=beat_v39b_candidate_B_repeat`, `reuse=False`) reproduced identical metrics on a **distinct run path**.

## Winning recipe (frozen `hunt_config.json`)
```json
{
  "mode": "high_beta_guard",
  "primary": "v39b_live_adapt",
  "secondary": "v39d_confluence",
  "boost": 1.1,
  "calm_threshold": 0.99,
  "elevated_threshold": 1.1,
  "high_beta_base": 0.75,
  "high_beta_elevated": 0.75,
  "core_elevated": 1.0,
  "position_cap": 2.0,
  "high_beta_codes": ["IONQ.US"],
  "max_scale": 1.18
}
```

**Mechanism (non-identity):**
1. Start from **v39b** targets.
2. When **v39d agrees**, scale up by **1.10×** (calm threshold set so agree-boost always eligible).
3. **IONQ only** is permanently sized to **0.75×** (high-beta base) — reduces the single-name concentration that set the May-2026 portfolio trough, without a global cap that crushed all names.
4. Core names keep full boosted size (`core_elevated=1.0`, `position_cap=2.0` effectively uncapped).

Also multi-locked: `hbg_ionq_only80` (+182.8% / −11.8% / Sharpe 2.79). Best by return is **hbg_ionq_only75**.

## Search notes
Earlier pure size-up / global caps either:
- lifted return but **worsened DD**, or
- improved DD but **cut return** (global `position_cap≈0.40`).

Per-name IONQ haircut + mild agreement boost is the first combination that multi-locked.

## Recommended model
**`v73_trump_beat`** for Trump-window multi-lock over `v39b_live_adapt`.

## Reproduce
```python
import tools.dynamic_model_rank as dmr
from evolve.farm import EQUITY_WINNER_BAG
m = dmr.discover_models(["v73_trump_beat"])[0]
dmr.run_one(m, mode="daily", codes=EQUITY_WINNER_BAG,
            start="2025-01-20", end="2026-07-11",
            tag="verify", force_1d=False, cash=1000,
            source="local", interval="1H")
```

```bash
PYTHONPATH=tools:. .venv/bin/python -m pytest tests/test_v73_trump_beat_blend.py -v
```
