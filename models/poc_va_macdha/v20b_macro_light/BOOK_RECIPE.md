# Usable book recipe — v20b_macro_light

**Goal:** highest *risk-adjusted* return with minimized drawdown, using all WORKING knowledge.

## What to run

```bash
# Engine + meta live in:
models/poc_va_macdha/v20b_macro_light/
runs/poc_va_v20b_macro_light/
```

Universe traded: **APLD, IONQ, TSLA, MU, SPY**  
Refs only (flat): **XLP** (macro), QQQ optional  
Dropped: **ARM**

## Stack (do not reorder casually)

1. **Primary SIDE** — per-symbol specialists (POC/VA + HTF MACD-HA + DNA flags)
2. **Secondary WHETHER/SIZE** — frozen v15 meta-XGB (`meta_xgb_final.json`, thr≈0.6)
3. **Risk** — half-Kelly + ATR stop/trail (v14/v16)
4. **Macro veto** — no new longs / flatten when XLP/SPY RS is in a defensive uptrend
5. **Universe** — drop ARM; do **not** hard-gate Mag7 (that killed capacity in v20)

## Results (2024-08 → 2026-07, 1H)

| Model | Return | Max DD | Sharpe | PF | n |
|-------|--------|--------|--------|----|---|
| **v20b (this)** | **+114%** | **−10.0%** | **2.23** | **3.04** | 101 |
| v15 winner (prev) | +130% | −13.2% | 2.13 | 2.68 | 130 |
| v16 meta+risk | +116% | −10.8% | 2.06 | 2.44 | 133 |
| v20 full dual-sleeve | +37% | −5.1% | 1.67 | 6.03 | 50 |
| v19 node-cloud | −38% | −68% | −0.12 | 0.91 | 374 |

## Intentionally NOT included

- Price-predicting ML as SIDE
- Full Coulling climax stack on 1H (v17 fail)
- Hard Mag7∧QQQ on large names as capacity killer (use as live advisory / soft size later)
- Random new tickers without DNA proof (hunt peers offline first)

## Live desk extras (advisory, not in engine yet)

- Volume-first breakouts; 22 EMA pullback zone; lost 200 EMA = structural break
- GEX/vol_z meta when historical OI exists
- XLP/SPY double-top bottom windows as *allow* overlay research
