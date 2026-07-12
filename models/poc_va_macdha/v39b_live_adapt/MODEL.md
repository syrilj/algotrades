# v39b_live_adapt

**Live-first react engine.** Nodes + fast VPA + adaptive size. Not a price predictor.

## Why this version

`v39` proved continuous Coulling helps quality (better DD/WR) but **cut return** on the WINNER bag. `v39b` keeps the philosophy and makes it **usable for live**:

| Knob | v39 | v39b live |
|------|-----|-----------|
| VPA look / vol SMA | 5 / 20 | **3 / 14** (faster) |
| Negative VPA weights | full | **~half** |
| Stand-aside floor | score ≤ −1.60 | **removed** |
| EMA bear | ×0.78 | **×0.90** mild |
| Score dynamics | static | **vpa_mom + vol_regime** |
| Streak | after win/loss only | **stack + mean-revert + live seed** |
| Mid-trade | fixed size | **shrink if VPA collapses** |
| Desk API | none | **`record_trade` / `live_adapt_snapshot`** |

## Mental model (live)

```
1. Structure nodes (POC/VAL) → where inventory sits
2. Fast VPA score + mom  → is volume agreeing right now?
3. EMA cloud             → mild path bias
4. Meta + streak         → how much capital this bar
5. After fill            → record_trade() adapts next plan
```

## Live adapt surfaces

```python
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
p = Path("models/poc_va_macdha/v39b_live_adapt/signal_engine.py")
spec = spec_from_file_location("v39b", p); m = module_from_spec(spec); spec.loader.exec_module(m)
eng = m.SignalEngine()
# ... generate signals ...
eng.record_trade(pnl=85.0, symbol="IONQ", tags={"vpa": 0.6})
print(eng.live_adapt_snapshot())
```

## H2H (WINNER bag 1H, 2024-08→2026-07, $1M)

| Model | Return | Sharpe | Max DD | WR | n |
|-------|--------|--------|--------|-----|---|
| **v39b_live_adapt** | **+365%** | **2.77** | -13.2% | **68%** | 144 |
| v38_research_stack | +310% | 2.65 | -12.5% | 66% | 140 |
| v39_vpa_score | +224% | 2.53 | **-10.3%** | 68% | 142 |

**Promoted** over v38 on Sharpe + return. DD slightly worse (accept for live capacity). Quality sleeve backup: `v39_vpa_score`.

## Desk

```bash
.venv/bin/python tools/trade_desk.py IONQ --model v39b_live_adapt
.venv/bin/python tools/vpa_scan.py --symbols TSLA,IONQ,APLD
```

## Forbidden

Hard climax entry stacks · price ML primary · hard VPA entry ANDs · freezing size after one loss forever
