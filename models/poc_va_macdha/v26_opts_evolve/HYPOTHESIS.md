# Hypothesis — v26_opts_evolve

**Version:** `v26_opts_evolve`  
**Family:** options on `poc_va_macdha` equity SIDE  
**Parent:** `v22_opts_live` (not v25 equity)

## Claim

v22 won because **options leverage + high-WR selective entries + evolved universe + partial-account compound**, not because of more filters. v26 keeps that stack and improves the path by:

1. **Concentrate** — at most one new best-of-day entry when multiple signals fire (compound path).  
2. **Volume expand gate** — only enter when daily volume ≥ 20d SMA (effort confirms intent).  
3. **React cut** — exit if underlying ≤ −8% from entry even if equity signal still on.  
4. **Streak size** — risk_pct ∈ [5%, 18%], up after wins, down after losses (bounded).  

Expected: full-window return ≥ v22 (~+60%) **or** better DD / PF with similar n; moonshot 30d windows still possible without full-account blowups.

## Finds applied

- Hunt SYNTHESIS: bags + atm10_21 + IONQ/AVGO/HOOD/MU evolution  
- Options playbook: cut losers / don’t hold dead premium  
- Volume meta: expand confirms  
- Anti-overfit: no new ML primary; freeze universe from hunt  

## Finds avoided

- Full-account compound (v24 DD −71%)  
- Stock-only v25 as growth engine  
- APLD-heavy sniper as options bag (hunt: APLD solo worst)  

## Kill criteria

If full window ret < v22 − 15pp **and** worse DD → fail, keep v22_opts_live.
