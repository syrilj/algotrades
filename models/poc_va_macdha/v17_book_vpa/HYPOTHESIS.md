# Hypothesis

**Version:** `v17_book_vpa`  
**Family:** `poc_va_macdha`  
**Date:** 2026-07-11

## Claim (one paragraph)

Starting from WINNER `v15_meta_xgb`, add Coulling/Wyckoff VPA primary gates (no-demand block, effort-vs-result, stopping-volume reclaim, topping/buying-climax blocks) plus Soros reflexivity (avoid chase after climax; prefer sustained confirm) and Dixit/Nalebuff commitment (enter only with credible volume confirmation). Meta XGB feature schema unchanged — books improve *whether* we take the side, not the booster inputs. Expect higher PF / lower DD via fewer weak-rally traps; trade count may fall.

## Finds applied

- Book synthesis: Coulling VPA (effort/result, stopping/topping, no demand)
- Soros: boom/bust self-reinforcing then self-defeating — block buying climax chase
- Thinking Strategically: credible commitment before acting
- Options guide: climax/high-vol regime = avoid naked directional chase (proxy via buying_climax)

## Finds avoided

- Do not replace primary side with price ML (`poc_va_xgb` any_edge false)
- Do not stack unrelated filters without book mapping

## Pass bar target

Must beat: PF ≥ 1.2, |DD| ≤ 25%, Sharpe ≥ 0.5, trades ≥ 40 on 2024-08..2026-07 window. Compare vs v15 portfolio Sharpe 2.13 / PF 2.68 / DD −13%.

## Kill criteria

If OOS fails → record fail and either (a) relax climax/effort gates or (b) port only `block_no_demand` + `allow_stopping_reclaim` into `poc_va_gex` volume meta.
