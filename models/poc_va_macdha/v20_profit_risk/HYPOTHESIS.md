# Hypothesis

**Version:** `v20_profit_risk`  
**Family:** `poc_va_macdha`  
**Date:** 2026-07-11  
**Sources:** [LSE Risk Management](https://londonstrategicedge.com/machine-learning/risk-management/), [Position Sizing](https://londonstrategicedge.com/machine-learning/risk-management/position-sizing/), [Drawdown Analysis](https://londonstrategicedge.com/machine-learning/risk-management/drawdown-analysis/) · builds on v12 / v14 / v15 / v16

## Claim (one paragraph)

Keep **v12 regime-router entries** (highest raw PnL engine) but replace naive full-size with an LSE-style **risk budget**: fixed-fractional risk to the ATR stop, half-Kelly confidence buckets, vol scaling, plus a **portfolio drawdown throttle / kill-switch** that v14 left as “manual only.” Goal: land between v12 money ($4.1k / $1k) and v15 smoothness (DD −13%) — target **end equity ≥ v14** with **|DD| ≤ 18%** and Sharpe ≥ v14.

## Why not just v16?

v16 stacked risk on **v15 meta** and *lost* Sharpe/PF vs WINNER (`beats_v15_sharpe_pf_dd: false`). Profit was already capped by the meta gate. v20 puts risk on the **profit engine (v12)**, not the already-defensive meta book.

## Mechanism

1. **Primary side** — `ROUTING.json` / v12 per-symbol specialists (unchanged entry logic).
2. **Confidence gate** — soft floor `min_confidence` (start 0.55 like v14); do **not** hard-zero via full-sample XGB (avoids v15 over-filter + leakage caveat on the profit path). Optional later: WF-stitched meta as a *size dampener only*.
3. **Per-trade risk (LSE fixed fractional)** — size so `$risk_to_stop = equity × risk_pct` with `risk_pct=0.01` default; stop distance = `1.5 × ATR`.
4. **Half-Kelly + vol scale (LSE position sizing)** — multiply by conf bucket `{0.35, 0.65, 1.0}` and `clip(med_atr/atr, 0.4, 1.25)`; `kelly_fraction=0.5` never full Kelly.
5. **In-trade (LSE cut losers / let winners run)** — hard stop `1.5 ATR`; arm trail at `+1.0 ATR`; trail `2.5 ATR`; soft HTF flicker ignored once armed (v14).
6. **Portfolio DD throttle (new — LSE drawdown awareness)**  
   - equity DD from peak `d`:  
     - `d < 5%` → size × 1.0  
     - `5–10%` → size × 0.5  
     - `≥ 10%` → **kill new entries** until recovery to `d < 5%`  
   - Hard account stop: flatten / pause if `d ≥ 15%` (research default; tune OOS).

## Finds applied

- v12: regime router = max total return on window  
- v14: ATR stop/trail + half-Kelly vol scale works (DD −39% → −24%)  
- MODEL.md: “max DD kill-switch” still open  
- v14 TRADE.md: portfolio DD pause was external — move **inside** engine

## Finds avoided

- Do not re-stack full Coulling/VPA gates on top (v17 over-filter FAIL)  
- Do not promote v16_wr80 / v18_wr90 (n=12 sniper) as core book  
- Do not use full-sample meta booster as hard gate on this profit path until WF stitch exists

## Pass bar target

Same window as peers (`2024-08-01` → `2026-07-11`, 1H, same 6 names):

| Metric | Must beat |
|--------|-----------|
| Total return | ≥ v14 (~+252%) **or** end$ ≥ v14 if slightly lower but DD much better |
| Max DD | **≤ 18%** (better than v14 −24%; stretch goal ≤ 15%) |
| Sharpe | ≥ 1.72 (v14) |
| PF | ≥ 1.79 (v14) |
| Trades | ≥ 40 |

Primary score for this draft: **Calmar / final equity under DD cap** — not Sharpe alone (v15 already owns that).

## Kill criteria

If OOS fails joint (return floor **and** DD cap) → `tools/findings.py record --status fail` and `FAILURE_PROTOCOL.md`. Do not add more filters; retune risk knobs or abandon.

## Open knobs

`risk_pct`, `dd_soft`, `dd_halt`, `dd_flatten`, `stop_atr`, `trail_atr`, `arm_trail_atr`, `kelly_fraction`, `min_confidence`
