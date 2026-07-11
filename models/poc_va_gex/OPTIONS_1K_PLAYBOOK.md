# Options playbook — $1,000 account (usable)

**Date:** 2026-07-11  
**Sources:** OIC *Options Strategies Quick Guide* (`books/options-strategies-quick-guide.pdf`), `GEX_GUIDE.md`, Coulling/Soros book findings, stock winners (`v20b_macro_light` / sniper sleeve), `tools/trade_desk.py` scanner.

**Honest limit:** We do **not** have a walk-forward options PnL backtest (no clean multi-year OI/premium history). This is a **rules playbook** that maps stock-model edge → option structure. Paper first.

---

## Verdict (which “model” for options?)

| Layer | Use | Why |
|-------|-----|-----|
| **SIDE / timing** | **Sniper DNA** (APLD/IONQ path from v18/v20b): QQQ trend + volume expand + block red-flag + **XLP/SPY defensive block** | Highest expectancy names; cheap enough premiums for $1k |
| **WHETHER** | Scanner (`trade_desk scan` / rotate) + live GEX snapshot | Only act when desk says buy/breakout *and* macro not defensive |
| **STRUCTURE** | Prefer **bull call debit spreads** (OIC); long calls only when debit ≤ ~10–15% of account | Defined risk; survives IV crush better than naked weeklies |
| **Avoid as options underlyings on $1k** | **MU** (ATM weekly ≈ multi‑thousand debit), naked **TSLA** size, short premium / iron condors | Capital, assignment, and undefined-risk don’t fit |

Stock **v15/v20b** is still the best *equity* book. For **options**, the best *mapping* is: **sniper timing + v20b macro veto + OIC debit structures** — not “trade MU like the stock model.”

---

## $1,000 capital reality (live snapshot-style)

1 contract = 100 shares of exposure. Rough ATM near-term debit × 100:

| Name | Fits $1k? | Notes |
|------|-----------|--------|
| **APLD** | Yes (~$100–150/contract typical) | Primary options name |
| **IONQ** | Yes (~$150–250) | Primary options name |
| **SPY** | Borderline | Cheap premium but **low IV** — needs clean trend; better as regime, not lottery |
| **TSLA** | Risky (~$300–500+) | 1 naked call = 30–50% of book; use **tight debit spread** only |
| **MU** | **No** for ATM weeklies | Premium alone can exceed $1k |

**Hard rules for $1k**

1. Max risk per idea: **$150–200** (15–20% of account).  
2. Max concurrent options ideas: **1** (sometimes 2 only if total risk ≤ $300).  
3. Never sell naked calls/puts on this size.  
4. Prefer **debit** defined-risk (bull call spread) over credit strategies until account ≥ ~$5–10k and margin understood.

---

## Greeks & “earnings / warnings” (must factor)

| Greek / risk | What to do |
|--------------|------------|
| **Delta** | Target **0.35–0.55** on the long leg (directional, not lottery 0.10 OTM). Spread short leg ~0.15–0.25. |
| **Theta** | Avoid 0–3 DTE lottery. Prefer **~14–45 DTE** so the stock model’s 1–5 day hold can work. |
| **Vega / IV** | If IV is already extreme and **earnings within 7 days**, skip or use a **spread** (long expensive IV, short further OTM to cut vega). After earnings, IV crush kills long premium even if stock is flat. |
| **Gamma** | Near expiry gamma spikes — fine for sniper *only* if already in profit and scaling out; otherwise stay ≥14 DTE. |
| **GEX** | **−GEX** (amplify) + our long signal = OK for calls/debit spreads. **+GEX** pin → smaller size or skip. |
| **Liquidity** | Bid–ask ≤ ~10–15% of mid; open interest not tiny. Skip wide markets. |

OIC reminder: examples ignore commissions; with $1k, **fees matter** — don’t overtrade.

---

## Structure map (from OIC guide → our book)

| Stock signal (model/scanner) | Options structure | When |
|------------------------------|-------------------|------|
| Sniper long (APLD/IONQ), QQQ ok, not defensive | **Bull call debit spread** | Default |
| Same + cheap IV / strong −GEX / vol expand | **Long call** (1 contract) | Only if debit ≤ $150 |
| High IV into event / unclear | **Stand aside** or very tight spread | Earnings, FOMC week if IV spiked |
| Defensive XLP/SPY uptrend | **No new longs** | Same veto as v20b |
| Bearish (we barely short) | Don’t force puts on $1k | Optional later: bear put spread |

Neutral OIC plays (iron condor, short straddle, covered call) need stock or large margin — **out of scope** for $1k directional catch of big moves.

---

## Workflow (scanner + model + options)

```
1) trade_desk rotate / scan  → candidate names (hot sector + model state)
2) Filter universe to APLD/IONQ (+ TSLA spread-only if exceptional)
3) v20b-style checks: XLP/SPY not defensive; QQQ trend ok for sniper
4) Live GEX snapshot: prefer −GEX or approaching call wall with room
5) Earnings calendar: if ≤7 DTE to earnings → skip naked; spread only or wait
6) Pick expiry 14–45 DTE; long delta ~0.40–0.50; debit spread width so max loss ≤ $150–200
7) Exit: stock model exit / cloud-macro flip / 50–100% of debit credit / 2–3 DTE left
```

Catching **big moves**: sniper names already have the vol asymmetry; options **leverage** that. Selectivity (macro + scanner + IV/earnings) is what keeps $1k alive.

---

## What would “perform best” (expected ranking for options)

1. **APLD/IONQ sniper timing + debit spreads** — best fit for capital + edge  
2. **v20b macro veto on top** — cuts defensive wipeouts (same lesson as stocks)  
3. **TSLA tight debit spreads** — occasional only  
4. **Full v15 six-name stock book traded as ATM options** — **worst** on $1k (MU impossible; overtrading theta)

---

## Next build (when you want code)

- `tools/options_picker.py`: given symbol + side from scanner, propose 1 debit spread (delta/IV/DTE/max loss ≤ budget)  
- Paper journal 20–30 trades before live  
- Do **not** promote an options “WINNER” until we can score defined-risk trades OOS


---

## Synthetic swing backtest (research)

**Script:** `models/poc_va_gex/research/options_swing_backtest.py`  
**Signals:** v20b APLD+IONQ entries  
**Pricing:** BS with IV = 20d realized vol (not exchange marks)  
**Start:** $1,000 · 1 contract · skip if premium > 25% of book  

| Variant | Final | Return | Max DD | n | WR |
|---------|-------|--------|--------|---|-----|
| **call ATM 14DTE + TP50/−40 SL** | **$1,564** | **+56%** | **−4.5%** | 17 | 53% |
| call OTM5% 21D + TP50/−40 | ~$1.4k+ | see JSON | | | |
| stock 20% clip (same signals) | $1,317 | +32% | −3.6% | 36 | 64% |
| call hold-to-model (no early) | worse than early TP/SL | | | | |

**Takeaways**

1. On $1k, **options can beat stock** on the same sniper signals (leverage) in this synthetic test.  
2. **Early profit take (+50%) / stop (−40%)** beat holding to the stock model exit — theta eats slow swings.  
3. **Slightly OTM / ~0.40Δ** is usable; deep OTM10% underperformed hold-to-model.  
4. Live: use `tools/options_picker.py` (debit spreads). Backtest used naked calls for simplicity.

Full table: `models/poc_va_gex/artifacts/OPTIONS_SWING_BACKTEST.json`
