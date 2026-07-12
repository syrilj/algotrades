# v39_vpa_score

**React to nodes + continuous VPA.** Not a price predictor.

## Mental model

```
Chart nodes (POC / VAL / VAH)  →  where inventory sits (supply/demand)
EMA cloud                     →  path tape is leaning (soft)
VPA (volume effort)           →  is the reaction real?
Meta XGB + genome             →  how much capital
```

Primary still chooses **SIDE**. VPA / cloud / nodes choose **WHETHER / HOW MUCH**.

## Stack

| Layer | Role |
|-------|------|
| Specialist primary (v23 DNA) | SIDE: POC/VA + HTF MACD-HA + routing |
| Continuous `vpa_score` | Coulling effort/result → size mult 0.42–1.22 |
| Demand node reaction | Near VAL/POC within 0.6 ATR + VPA≥0 → ×1.10 |
| EMA cloud (9/21/55) | Bull path ×1.06, bear path ×0.78 |
| Meta XGB + vol_z + RS | Continuous soft meta size |
| Genome risk + streak | After win/loss mults |
| Soft climax exit | Unarmed + climax_recent + weak VPA → exit |

## VPA score components

| Signal | Weight | Meaning |
|--------|--------|---------|
| stopping_reclaim | +1.00 | Absorption then reclaim |
| no_supply_test | +0.70 | Dip on low vol after stop |
| spring | +0.55 | Failed break of lows |
| confirm_up | +0.45 | Price↑ volume↑ harmony |
| healthy_pull | +0.15 | Dip on drying volume |
| no_demand | −0.75 | Weak rally / trap |
| buying climax recent | −0.85 | Don’t chase fireworks |
| effort_anomaly | −0.55 | Wide move thin volume |
| topping recent | −0.50 | Distribution into strength |
| upthrust | −0.60 | Bull trap |
| dump | −0.70 | Selling pressure |

Stand-aside floor: `vpa_score ≤ −1.60` zeroes size for that bar (extreme trap only).

## Forbidden (research fails)

- Hard EMA200 / hard vol entry gates  
- Full Coulling climax hard-stack on 1H entry (`v17`)  
- Price-predict ML as primary  
- Hard structure blocks that kill capacity  

## H2H results (2026-07-12)

**WINNER bag 1H** (`TSLA MU SPY IONQ APLD + XLP QQQ`, 2024-08→2026-07, $1M):

| Model | Return | Sharpe | Max DD | WR | n | PF |
|-------|--------|--------|--------|-----|---|-----|
| **v38 (WINNER)** | **+310%** | **2.65** | -12.5% | 66% | 140 | 3.60 |
| v39_vpa_score | +224% | 2.53 | **-10.3%** | **68%** | 142 | 3.57 |

**Verdict:** do **not** promote over v38 on this bag (return/Sharpe lag). Quality↑ (DD/WR) capacity↓ (return) — same shape as light VPA research (`v17b`).  

**Screen mixed bag** (broader names): v39 **beat** v38 (+13.3% vs +2.4%, better DD). Suggests continuous VPA helps outside high-beta specialist DNA — treat as **sleeve / meta research**, not full WINNER replace.

### Next ablations
1. Drop stand-aside floor (`score ≤ -1.60`)  
2. Drop EMA bear cut  
3. Halve negative Coulling weights  
4. Use score only for soft **exits**, keep v38 entry sizing  

## Files

| File | Role |
|------|------|
| `signal_engine.py` | Engine |
| `meta_xgb_final.json` | Frozen booster from v37/v38 lineage |
| `meta_config.json` | Feat cols + genome + research tags |
| `config.json` | Backtest window / universe |
| `HYPOTHESIS.md` | Claim + pass/kill |

## How to run

```bash
# Desk plan (when registered in trade_desk)
.venv/bin/python tools/trade_desk.py IONQ --model v39_vpa_score

# Evolve / rank (if pipeline knows the version folder)
.venv/bin/python tools/evolve_pipeline.py rank --models v39_vpa_score,v38_research_stack

# Live VPA tags (sibling research tool)
.venv/bin/python tools/vpa_scan.py --symbols TSLA,IONQ,APLD
```

## Options / GEX note

Live options walls (call wall / put wall / flip) remain a **desk confluence** layer via `poc_va_gex` / trade desk — not baked into this equity engine’s backtest (no reliable historical OI). Philosophy still applies live: nodes + VPA first, GEX scales size.
