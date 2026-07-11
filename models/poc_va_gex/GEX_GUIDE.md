# GEX + Options Flow Guide (for stock entries)

**Purpose:** Explain the math of dealer gamma exposure (GEX), how negative/positive GEX changes price behavior, how OTM call volume and 2σ volume bursts fit in, and how we will build a **new** options-aware layer **without replacing** the existing stock models (`v15_regime` / `v16_wr80`).

**Status:** Research scaffold. Stock winners stay frozen. This family is `poc_va_gex`.

**Date:** 2026-07-11

---

## 1. Big picture — two models, one book

```
┌─────────────────────────────────────────────────────────────┐
│  STOCK PRIMARY (keep)                                        │
│  POC/VA + HTF MACD-HA + VWAP/vol/red-flag + QQQ regime       │
│  → chooses SIDE (long / flat)                                │
│  v14 risk / v15 regime / v16 wr80 sleeve                     │
└───────────────────────────┬─────────────────────────────────┘
                            │ candidate entry at time t
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  OPTIONS META (new — poc_va_gex)                             │
│  GEX regime + OTM call/put flow + volume z-score             │
│  → chooses WHETHER / HOW MUCH (and optionally wait/skip)     │
└─────────────────────────────────────────────────────────────┘
```

This matches our locked playbook (`models/_shared/PLAYBOOK.md`):

> Primary (rules) → SIDE · Secondary (meta) → WHETHER / HOW MUCH · Risk → stops/Kelly

We do **not** throw away stock DNA. Options/GEX is a **confluence filter / size scaler**, same role as the QQQ regime gate in v15.

---

## 2. The math — Greeks you need

### 2.1 Delta (Δ)

How much the **option price** moves when the **stock** moves $1.

Under Black–Scholes (European options):

\[
d_1 = \frac{\ln(S/K) + (r + \sigma^2/2)T}{\sigma\sqrt{T}}
\]

\[
\Delta_{\text{call}} = \Phi(d_1), \qquad \Delta_{\text{put}} = \Phi(d_1) - 1
\]

where \(\Phi\) is the standard normal CDF, \(S\) spot, \(K\) strike, \(T\) years to expiry, \(r\) rate, \(\sigma\) IV.

### 2.2 Gamma (Γ)

How much **delta** changes when the stock moves $1. Second derivative of option value to spot:

\[
\Gamma = \frac{\partial \Delta}{\partial S} = \frac{\partial^2 V}{\partial S^2}
= \frac{\varphi(d_1)}{S\,\sigma\sqrt{T}}
\]

where \(\varphi\) is the standard normal PDF.

**Facts that matter for trading:**

- Γ is the **same for calls and puts** with the same \(S,K,T,\sigma\).
- Γ peaks **ATM** and near expiry; OTM/ITM Γ is smaller.
- Long options → positive Γ. Short options → negative Γ.

Sources: [Wikipedia — Greeks (finance)](https://en.wikipedia.org/wiki/Greeks_(finance)), [Investopedia — Gamma](https://www.investopedia.com/terms/g/gamma.asp).

### 2.3 Why dealers care (the hedging story)

Market makers who **sell** options to customers are typically **short gamma**. To stay delta-neutral they hedge with stock:

| Stock move | Short-gamma dealer must… | Effect on market |
|------------|--------------------------|------------------|
| Price ↑    | **Sell** stock (delta rose against them) | Adds selling into strength |
| Price ↓    | **Buy** stock (delta fell) | Adds buying into weakness |

That is **amplification** → associated with **negative GEX** regimes (dealers short gamma in aggregate).

If dealers are **long gamma** (customers net short, or dealers long):

| Stock move | Long-gamma dealer must… | Effect |
|------------|-------------------------|--------|
| Price ↑    | **Buy** less / sell stock | Fades the move |
| Price ↓    | **Sell** less / buy stock | Fades the move |

That is **pinning / mean-reversion** → **positive GEX**.

> Mental model: **+GEX = shock absorber**, **−GEX = amplifier**. Your stock technicals fire either way; GEX tells you whether the tape will *help* or *fight* the move.

---

## 3. GEX formula (how we compute it)

There is no single exchange “official GEX.” Research stacks use a **dealer-sign convention**. The common practical form:

### 3.1 Per-contract gamma dollars

For one option contract (multiplier 100 for US equity options):

\[
\text{GEX}_{i} = \Gamma_i \cdot \text{OI}_i \cdot 100 \cdot S^2 \cdot 0.01
\]

Interpretation: approximate **dollar delta change** in the hedge book for a **1% move** in \(S\) (the \(S^2 \cdot 0.01\) scaling). Some vendors use \(S\) instead of \(S^2\cdot 0.01\); what matters is **consistency** and **sign**.

### 3.2 Call vs put sign (dealer assumption)

Standard retail GEX assumption: **customers buy calls and puts; dealers are short both** → dealer gamma is **negative** of customer gamma. Aggregating as:

\[
\text{Net GEX} = \sum_{i \in \text{calls}} +\text{GEX}_i \;+\; \sum_{j \in \text{puts}} -\text{GEX}_j
\]

(Equivalent: calls contribute positive customer GEX, puts negative — then flip for dealer.)

**Important caveat:** This assumption is wrong when customers are heavily short (e.g. covered calls, put selling). Treat GEX as a **regime proxy**, not gospel. Validate with walk-forward like every other filter.

### 3.3 Spot gamma / flip level

- Plot GEX by strike → largest |GEX| strikes are **magnets / walls**.
- **Zero-gamma / flip level**: spot where net GEX crosses 0. Above flip often more +GEX (pinny); below more −GEX (volatile). Exact construction varies by vendor.

### 3.4 LSE feed (London Strategic Edge) — what we actually get

**Auth:** `LSE_API_KEY` in repo `.env` (gitignored). Client: `from lse import LSE`.

**Chain fields present:** strike, expiry, contract_type, underlying_price, gamma, delta, iv, volume_today, premium_today.

**Missing:** open interest. Classic OI-weighted GEX therefore **cannot** be computed from LSE alone.

**Proxy we use** (`research/lse_gex_snapshot.py`):

\[
\text{DealerGEX}_{\text{volw}} = -\Gamma \cdot w \cdot 100 \cdot S^{2} \cdot 0.01
\]

where \(w =\) `volume_today` (fallback `premium_today`). Near-spot net (±10% of \(S\)) sets regime:

| Near-spot dealer GEX | Regime label | Bias for stock longs |
|----------------------|--------------|----------------------|
| \(> 0\) | `positive_gex_pin` | Prefer pullbacks / skip chase |
| \(< 0\) | `negative_gex_amplify` | Trend continuation more likely |
| \(= 0\) | `flat` | No options confluence |

**Flow layer:** `options_flow(min_premium=25k)` → call:put premium ratio + OTM call premium as participation signals (meta only; never flips SIDE).

**Caveat:** Volume-weighted GEX is **intraday activity**, not inventory. Do not treat it as SpotGamma-style OI GEX in audits.

Live artifact: `artifacts/lse_gex_flowweighted.json`.

### 3.5 What we can compute today vs what needs paid data

| Input | Live (now) | Historical backtest |
|-------|------------|---------------------|
| Option chain OI, IV, strike | **yfinance** snapshot | **Hard** — Yahoo does not give clean multi-year OI history |
| Stock volume z-score (2σ) | Easy on OHLCV | Easy — use immediately |
| Full historical GEX surface | Need ORATS / CBOE / Polygon / similar | Required for honest OOS GEX tests |

**Honest path:**  
1. Ship **volume 2σ + live GEX snapshot confluence** as research tools now.  
2. Do **not** claim backtested GEX edge until we have historical options OI.  
3. Meanwhile backtest the **volume z-score meta-filter** on the stock primary (that part is audit-clean).

---

## 4. Your intuition, formalized

### 4.1 “Negative GEX amplifies; positive pins”

Yes — that is exactly the dealer-hedging map in §2.3. For **long stock entries** (our book is long-biased):

| GEX regime | What it means for longs | How meta layer should act |
|------------|-------------------------|---------------------------|
| **−GEX** | Moves can runaway; winners extend, losers cascade | Prefer **trend/breakout** entries; size normal or up; wider trails |
| **+GEX** | Mean-reversion / pin near large OI strikes | Prefer **pullback-to-VWAP/POC** entries; size down or skip chase entries |
| Near **flip** | Regime unstable | Reduce size / require extra stock confluence |

### 4.2 “OTM calls pouring in ⇒ move coming?”

OTM call volume/OI rising means:

- Speculative upside demand **or** dealers need to hedge → can create **upward gamma / delta chase** if dealers are short those calls.
- Alone it is **noisy**. Combine with:
  - Volume on the **underlying** ≥ 2σ (see §4.3)
  - Spot approaching call wall / leaving put wall
  - Our stock primary already green (HTF HA, not red-flag)

**Confluence rule (proposed, to be OOS-tested):**

```
stock_primary_long
AND underlying_volume_z >= 2
AND (net_gex < 0 OR otm_call_volume_z >= 2)
→ allow full size
ELSE IF stock_primary_long AND net_gex > 0 AND volume_z < 1
→ half size or skip (pin regime, weak participation)
```

### 4.3 “Volume always precedes price” + 2 standard deviations

On the **underlying** (not the option):

\[
z_t = \frac{V_t - \mu_{V,n}}{\sigma_{V,n}}
\]

with lookback \(n\) (e.g. 20 sessions). **\(z \ge 2\)** ≈ top ~2.5% volume days under normality (real volume is fat-tailed, so treat 2σ as “unusually large,” not exact probability).

Why it helps our stack:

- Our FEATURE_INSIGHTS already show **vol confirm / block red-flag** (price↑ vol↓) matter for high-beta.
- 2σ volume is a **stricter** cousin of `require_volume_expand` — fewer trades, higher conviction.
- Fully backtestable on existing OHLCV (no options history needed).

---

## 5. How this plugs into *your* stock models

### 5.1 Model map (current winners — do not overwrite)

| Version | Role | WR / notes |
|---------|------|------------|
| `v15_regime_specialists` | Broad book + QQQ trend gate | ~64% WR, Sharpe ~1.78, DD −17% |
| `v16_wr80` | Sniper sleeve APLD+IONQ | ~83% WR, n≈12 — thin |
| **`poc_va_gex` (new)** | Options/GEX + volume-z **meta** | Research — not promoted until OOS pass |

### 5.2 Integration pattern (code-level)

```
SignalEngine_stock.generate(data_map)  →  raw size in [-0,1]
GexMeta.scale(code, timestamp, raw_size, gex_state, vol_z)
  →  final_size ∈ {0, 0.25, 0.5, 1.0}
```

`GexMeta` never flips long→short. It only **zeros or downsizes**. That keeps audit trail clean: stock model still owns side.

### 5.3 Features the new model will log (for walk-forward)

At each stock-candidate entry time \(t\):

| Feature | Definition | Backtestable now? |
|---------|------------|-------------------|
| `vol_z_20` | Underlying volume z-score | Yes |
| `vol_z_ge2` | `vol_z_20 >= 2` | Yes |
| `net_gex` | Σ dealer GEX from chain | Live yes / hist needs vendor |
| `gex_sign` | sign(net_gex) | Live yes |
| `gex_norm` | net_gex / (ADV$ or shares) | Live yes |
| `call_wall` | Strike with max call GEX | Live yes |
| `put_wall` | Strike with max put GEX | Live yes |
| `dist_call_wall` | (call_wall − S)/S | Live yes |
| `otm_call_vol_z` | Volume z on OTM calls | Live partial |
| `iv_skew` | IV(25Δ put) − IV(25Δ call) | Live yes |

Label = **actual trade PnL from stock primary** (true meta-labeling), not “5-bar return.” That is the lesson from failed `poc_va_xgb`.

---

## 6. Research plan (proper order — no overfit)

1. **Volume-z meta only** on v15 candidates (full history we already have). Walk-forward: does `vol_z_ge2` lift OOS WR/expectancy?
2. **Live GEX dashboard** via LSE (`lse_gex_snapshot.py`) — volume-weighted proxy + flow; cross-check Yahoo OI snapshot when useful. Manual confluence journal 2–4 weeks.
3. **Historical options OI / dated GEX** still needed for a true GEX walk-forward; LSE live flow is for meta journal + forward paper until history exists.
4. **Combine** stock primary + vol_z + GEX sign in meta layer; promote only if `PASS_BAR.json` clears.
5. Keep `v16_wr80` as optional sniper sleeve; GEX meta targets the **broader** book (v15 path).

---

## 7. Worked numeric toy example

Spot \(S=100\), ATM call & put, \(\sigma=30\%\), \(T=7/365\), \(r=0\), OI_call=10,000, OI_put=8,000.

1. Compute \(\Gamma\) from BS (~ large ATM).
2. \(\text{GEX}_{\text{call}} = +\Gamma \cdot 10000 \cdot 100 \cdot 100^2 \cdot 0.01\)
3. \(\text{GEX}_{\text{put}} = -\Gamma \cdot 8000 \cdot 100 \cdot 100^2 \cdot 0.01\)
4. Net GEX = call + put terms. If calls dominate OI, net may be **positive** near ATM → pin risk. If puts dominate or we flip dealer sign, interpretation changes — **document the sign convention in code**.

(Script: `research/gex_snapshot.py` prints live numbers for a ticker.)

---

## 8. Risks & audit traps

- **Sign convention bugs** flip +GEX/−GEX and will invent fake edges.
- **OI lag**: end-of-day OI ≠ intraday; do not pretend tick-GEX without tick OI.
- **Index vs single-name**: SPX/QQQ GEX is cleaner than IONQ/APLD (sparse chains).
- **Survivorship / window**: same 2y limit as stock work.
- **Vanity WR**: GEX filter that cuts to 10 trades at 90% WR without OOS is a fail under playbook.

---

## 9. File map

| Path | Role |
|------|------|
| `models/poc_va_gex/GEX_GUIDE.md` | This document |
| `models/poc_va_gex/HYPOTHESIS.md` | One-paragraph hypothesis |
| `models/poc_va_gex/research/gex_snapshot.py` | Yahoo/yfinance OI-based GEX snapshot |
| `models/poc_va_gex/research/lse_gex_snapshot.py` | LSE volume/flow-weighted GEX + OTM call flow |
| `models/poc_va_gex/research/volume_z_meta.py` | Backtestable vol-z study on stock trades |
| `.env` / `.env.example` | `LSE_API_KEY` (never commit `.env`) |
| `models/poc_va_macdha/*` | **Unchanged** stock primary / sleeves |

---

## 10. Bottom line

Your idea is directionally right:

- **−GEX ⇒ amplify** (good for trend longs if you’re already aligned).
- **+GEX ⇒ pin** (fade chasing; prefer pullbacks or skip).
- **OTM call floods + 2σ underlying volume** ⇒ participation confirmation.
- Implement as **meta on top of stock models**, validate volume-z first (data we have), then GEX when historical OI exists.

Next concrete action: run `volume_z_meta.py` on v15 trades; run `gex_snapshot.py` on TSLA/QQQ for a live read.
