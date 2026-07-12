# What made the v39 line good

## The story in one page

We did **not** invent a new side predictor. We taught the engine to **react** to volume + inventory nodes the way Coulling/Wyckoff describe.

### v39 (first try) — too strict
- Continuous Coulling score with **heavy** negative weights
- Stand-aside floor (`score ≤ −1.60` → size 0)
- Strong EMA bear cut (×0.78)
- Result: better DD/WR, **worse return** vs v38 (+224% vs +310%) → **do not promote**

### v39b (what you like) — the fix
| Knob | Why it worked |
|------|----------------|
| **Halve negative VPA weights** | Stop starving good longs on noisy 1H |
| **Remove stand-aside floor** | Never hard-zero size; only soft mults |
| **Mild EMA bear (×0.90)** | Path bias, not a brick wall |
| **Faster sensors (look 3 / SMA 14)** | Volume story updates in 1–3 hours |
| **`vpa_mom` + `vol_regime`** | Lean in when effort improves; trust volume more when tape is loud |
| **Live streak + `record_trade()`** | Size adapts after wins/losses without retrain |
| **Primary SIDE frozen** | Still specialist POC/VA DNA — books only size **how much** |

**Full bag:** +365% ret · Sharpe **2.77** · DD −13.2% · n=144 · PF 3.65  
**vs v38:** +310% · 2.65 · −12.5% · n=140  

### Holdout (anti-overfit)
| Window | v39b ret / Sharpe | v38 ret / Sharpe |
|--------|-------------------|------------------|
| Early 2024-08→2025-06 | +193% / 3.16 | +206% / 3.22 |
| Late 2025-07→2026-07 | **+68% / 2.55** | +63% / 2.55 |
| Full | **+365% / 2.77** | +310% / 2.65 |

Late holdout still works. Early is close (v38 slightly better). Full compounds in favor of v39b.

### v39c (failed)
Dual-speed blend + extra DD cut **hurt** full return (280% / 2.58).

### v39d (failed)
A+ confluence size + calmer VPA exits → +311% / 2.72 (fewer trades). Over-calming exits hurt compounding.

**Lesson:** v39b’s slightly aggressive live exits + light VPA sizing is the sweet spot. Further engine knobs regressed. Next gains = paper loop / IB process, not more filters.

## How to trade it
```bash
.venv/bin/python tools/trade_desk.py IONQ --model v39b_live_adapt
# or --model auto  (now prefers WINNER.json)
```
