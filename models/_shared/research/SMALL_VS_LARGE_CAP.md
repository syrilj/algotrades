# Small-cap vs large-cap: why the edge splits (saved research list)

**Status:** Research intuition — **do not promote** a 95% WR model yet.  
**Date:** 2026-07-11  
**Keep:** This file is the durable checklist for future confluence / dual-sleeve work.

---

## 1. What the data actually shows

Base book (`enriched_trades.csv`, v14-path, n=221):

| Code | n | WR | Avg return % | Bucket |
|------|---|----|--------------|--------|
| APLD | 27 | **77.8%** | **+3.34** | Small / high-beta story |
| IONQ | 31 | **64.5%** | **+2.89** | Small / high-beta story |
| TSLA | 37 | 62.2% | +0.36 | Large high-beta |
| MU | 89 | 57.3% | +0.60 | Large semi |
| SPY | 7 | 57.1% | +0.02 | Index |
| ARM | 30 | 53.3% | −0.37 | Large / choppy |

Under `f_qqq_trend` only:

| Code | n | WR | Win avg % | Loss avg % |
|------|---|----|-----------|------------|
| APLD | 9 | **88.9%** | +4.74 | −1.0 |
| IONQ | 6 | **83.3%** | +4.33 | −0.6 |
| TSLA | 17 | 76.5% | +2.75 | −1.6 |
| MU | 41 | 63.4% | +3.55 | −1.5 |
| ARM | 9 | **44.4%** | +4.82 | **−3.4** |

Engine loop to ≥80% WR only cleared after **dropping TSLA + MU** → universe `{APLD, IONQ}`, n≈12–15, WR≈83–87%. That is a **sleeve**, not proof the same DNA works on megacaps.

Volatility / liquidity (same window OHLCV):

| Code | Daily vol % | p95 |$| move % | Vol CV | Mean $ volume |
|------|-------------|---------------|--------|---------------|
| APLD | 3.07 | 5.64 | 1.36 | ~$63M |
| IONQ | 2.59 | 4.70 | 1.12 | ~$124M |
| MU | 1.61 | 3.23 | 0.96 | ~$1.2B |
| TSLA | 1.38 | 2.88 | 0.78 | ~$3.7B |

FEATURE_INSIGHTS DNA: same flags (VWAP, vol expand, red-flag) show **large positive lift on APLD**; on TSLA/MU many lifts are **near-zero or negative**. One rulebook ≠ one market.

---

## 2. Why this works on small caps (theory grounded in findings)

1. **Travel distance** — POC/VA + MACD-HA needs the price to *leave* value. APLD/IONQ daily vol ~2.5–3%+; TSLA/MU ~1.4–1.6%. Same signal, less room → more scratch/chop losses.
2. **Asymmetric payoff** — Small-cap wins (~4–5%) dwarf losses (~0.6–1%) under QQQ trend. Large names: smaller wins and/or fatter ARM-style losers → WR and expectancy both suffer.
3. **Volume expansion is informative** — Thin dollar books: a real vol spike + VWAP hold ≈ genuine participation. Megacaps always trade; `vol_expand` is noisier (MU DNA lift weak / mixed).
4. **Fewer competing “theories”** — Megacaps are pinned by options GEX, Mag7 rotation, index arb, news desks. Our stock primary is a *microstructure* model; it wins when microstructure dominates. LSE snapshots show large names live in rich −/+ GEX regimes; sparse-chain names (APLD/IONQ) are mostly equity-flow stories.
5. **Low institutional / HFT crowding (desk intuition + data-compatible)** — Names like APLD/IONQ are not heavily warehouse’d by multi-strat / index / options desks the way TSLA/MU/SPY are. Less competing alpha → POC/VA + volume expansion can still “matter” for a few bars. Observable proxies we already have: lower mean $ volume (~$60–120M vs multi-billion), higher volume CV, sparse/absent options GEX. **Implication:** keep hunting *similar* under-owned small/mid names (same vol + $vol + DNA-lift profile) — do **not** assume every small cap works; assume edge decays as a name gets institutionalized.
6. **Sample honesty** — Jumping WR by dropping names is **selection**, not alchemy. Audit risk if sold as “the model is 85% on everything.”

---

## 3. Dual strategies (approach each bucket differently)

Do **not** force one filter stack. Keep stock primary → SIDE; meta → WHETHER/SIZE.

### Sleeve A — Small-cap sniper (current v16 path)

- **Universe:** APLD, IONQ (+ future peers only after same DNA lift proof).
- **Gates:** QQQ trend + vol expand + block red-flag.
- **Goal:** High WR / high PF, low trade count. Accept thin n.
- **95% WR intuition (later):** add confluence only if train+OOS both lift — candidates: stricter VA reclaim, 2σ volume, LSE OTM-call flood *if* chain exists, hold-for-extension only when −GEX on QQQ. **Not frozen.**

### Sleeve B — Large high-beta (TSLA / MU / ARM)

- **Different DNA**, not “more filters on Sleeve A.”
- **Primary tweaks to research:** Mag7 breadth gate (already partially tested), require pullback-to-VWAP in **+GEX**, allow breakout continuation only in **−GEX** (LSE volw proxy), wider stops / longer hold (chop tax), **block** ARM-style dump days harder.
- **Meta:** LSE flow call:put + near-spot GEX sign + vol_z≥2 — scale/skip only.
- **Success metric:** expectancy + Sharpe/DD first; WR secondary (realistic band ~65–75% OOS if edge exists).

### Sleeve C — Index (SPY)

- Treat as **regime / hedge / timing**, not momentum specialist.
- Prefer mean-reversion or “risk-on confirm” role for Sleeve A/B; do not chase 80%+ WR here.

### Book construction

```
Book = wA * SleeveA + wB * SleeveB(+GEX meta) + optional SleeveC
```

v15-style broad book ≈ capital / Sharpe engine.  
v16-style sniper ≈ high-WR satellite.  
**Do not merge into one vanity WR number.**

---

## 4. Path toward ~95% WR (intuition only — not a promote target)

Honest constraints:

- At n=12 and WR=83%, Wilson CI is wide; **95% is not statistically claimed**.
- Playbook: WR alone is vanity; need OOS expectancy, PF, DD, min trade count (`PASS_BAR.json`).

Research queue (save; run later for confidence):

1. [ ] Journal LSE GEX/flow daily vs Sleeve A/B candidates (2–4 weeks).
2. [ ] Rebuild FEATURE_INSIGHTS **separately** for large-cap bucket (do not reuse APLD DNA).
3. [ ] Walk-forward: QQQ −GEX + vol_z≥2 as meta on **TSLA/MU only**.
4. [ ] Peer search: other names with APLD-like vol + dollar-volume + DNA lift + **low institutional footprint** (not random small caps; avoid names that just IPO’d into heavy options/ETF flow).
5. [ ] Only if train+OOS WR≥90% **and** n≥25 **and** PASS_BAR: consider “ultra-sniper” experiment — still label as sleeve.
6. [ ] Never flip SIDE with options/ML; meta only.

---

## 5. What we are explicitly NOT doing now

- Not freezing a 95% model.
- Not deleting large names forever — they need a **different** approach.
- Not treating volume-weighted LSE GEX as OI inventory GEX.
- Not overwriting current stock winners with GEX primary.

---

## 6. Pointers

| Artifact | Role |
|----------|------|
| `runs/poc_va_wr80/artifacts/ENGINE_LOOP.json` | Drop-path to APLD/IONQ |
| `runs/poc_va_wr80/artifacts/FEEDBACK_LOOP.json` | Filter WR by code |
| `runs/poc_va_wr80/artifacts/enriched_trades.csv` | Per-trade features |
| `models/poc_va_macdha/FEATURE_INSIGHTS.json` | Per-name DNA lifts |
| `models/poc_va_gex/artifacts/lse_gex_flowweighted.json` | Live large-name options regime |
| `models/poc_va_gex/GEX_GUIDE.md` | Meta architecture |

**Bottom line:** Small-cap edge is real *for this primary* because of volatility, payoff asymmetry, and informative volume. Large names need regime/GEX/Mag7-native strategies. Save this list; build confidence with further research before any 95% claim.
