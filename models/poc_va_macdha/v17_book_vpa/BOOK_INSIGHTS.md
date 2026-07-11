# Book Insights → Model Edges (v17)

Sources in `books/`:

1. **Anna Coulling — Volume Price Analysis**
2. **George Soros — The Alchemy of Finance**
3. **Dixit & Nalebuff — Thinking Strategically**
4. **Options Strategies Quick Guide**

## Mapped rules

| Book idea | Quant signal | Gate |
|-----------|--------------|------|
| Effort vs result (Wyckoff) | Wide spread + low volume = anomaly | `require_effort_ok` |
| No demand | Up bar + low volume | `block_no_demand` (+ existing `block_red_flag`) |
| Stopping volume | After decline: high vol + narrow spread | `stopping_volume` → `allow_stopping_reclaim` |
| Topping / buying climax | High/extreme vol into rally | `block_topping_volume`, `block_buying_climax` |
| Reflexivity boom→bust | Sustained confirm then climax fails | `reflexive_up` prefer; climax block |
| Credible commitment | Act only with volume confirmation | `require_commitment` |
| Options: high-vol hurts shorts/straddles; climax = regime shift | Buying climax as realized-vol spike proxy | Block directional chase at climax |

## Why not retrain meta yet

`meta_xgb_final.json` feat_cols are frozen. Book edges are **primary filters** so we isolate whether VPA rules lift expectancy without contaminating the booster.
