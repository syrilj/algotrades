# What went wrong on v19 trades

**Date:** 2026-07-11  
**Artifacts:** `TRADE_REGIME_DIAG.json`, `MACRO_GATE_LIFT.json`

## Verdict

Node+cloud was fine; the book blew up trading **defensive / risk-off** tapes with one global long book. Macro/sector regime was the missing factor.

## Numbers (374 round-trips)

| Slice | n | WR | Exp | PnL |
|------|---|----|-----|-----|
| All v19 | 374 | 50% | +0.20 | −$380k |
| Defensive XLP/SPY | 43 | 44% | −0.82 | −$321k |
| Risk-on XLP/SPY | 207 | 53% | +0.43 | +$253k |
| Large (TSLA/MU/ARM) | 200 | 46% | −0.30 | −$533k |
| APLD in QQQ-up | 70 | 61% | — | +$339k |

## Prior research ignored

QQQ trend / Mag7 sleeves, small vs large DNA, volume expand — all already WORKING in findings.

## XLP/SPY double-top

Downtrend RS + two similar peaks + break below trough → bottom allow window. 4 confirms in sample.

## Fix

`v19b_node_macro`: block defensive; allow risk_on ∨ dt_bottom; volume expand.
