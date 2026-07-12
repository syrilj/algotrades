# Usable book recipe — v23_devin_overlay

**Goal:** beat v20b's risk-adjusted returns by layering a volume-z
conviction overlay onto the proven v20b meta-XGB stack.

## What to run

```bash
models/poc_va_macdha/v23_devin_overlay/
runs/poc_va_v23_devin_overlay/
```

## Stack

1. **Primary SIDE** — same per-symbol specialists as v20b (POC/VA + HTF MACD-HA + DNA flags)
2. **Secondary WHETHER/SIZE** — frozen v15 meta-XGB (`meta_xgb_final.json`, thr=0.6)
3. **Conviction overlay** — v20b proba + `volume_z` boost (`sector_rs` / `qqq_rs` reserved, currently disabled)
4. **Risk** — v20b half-Kelly + ATR stop/trail
5. **Macro veto** — same XLP/SPY defensive block as v20b
6. **Universe** — same as v20b: APLD, IONQ, TSLA, MU, SPY; XLP macro, QQQ optional; ARM dropped

## Overlay details

- `volume_price_state` now computes a 20-day volume z-score (`vol_z`)
- `_volume_z_boost(vol_z)` maps prior-bar vol_z to a small proba delta:
  - `vol_z >= 2.0` → +0.03
  - `vol_z >= 1.0` → +0.015
  - `vol_z < -1.0` → -0.03
  - `vol_z <  0.0` → -0.015
- Sector/QQQ RS scores are computed but currently disabled in the proba path
  (they had no measurable additive lift in this window; reserved for future research)

## Results (2024-08 → 2026-07, 1H)

| Model | Return | Max DD | Sharpe | PF | n |
|-------|--------|--------|--------|----|---|
| **v23_devin_overlay (this)** | **+130%** | **−9.06%** | **2.21** | **3.54** | **92** |
| v20b_macro_light (prev best) | +113% | −10.0% | 2.23 | 3.04 | 101 |

## Intentionally kept from v20b

- XLP/SPY defensive block
- Drop ARM
- Frozen meta-XGB (no retraining)
- Half-Kelly ATR risk management

## PASS_BAR

- profit_factor: 3.54 >= 1.2 ✅
- max_drawdown: -0.0906 <= 0.25 ✅
- sharpe: 2.21 >= 0.5 ✅
- trade_count: 92 >= 40 ✅
