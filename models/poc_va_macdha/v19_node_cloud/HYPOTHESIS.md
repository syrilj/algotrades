# Hypothesis

**Version:** `v19_node_cloud`  
**Family:** `poc_va_macdha`  
**Date:** 2026-07-11

## Claim (one paragraph)

Instead of predicting the next move, **react**: treat volume-profile levels (VAL / POC / VAH) as **nodes** (price magnets), use an **MA cloud** (EMA ribbon) to decide which node price is traveling toward, and only take longs when the cloud is bullish and there is a clear upside magnet with room to run. Exit at the target node or when the cloud flips. This is rules-primary SIDE — no price ML. Live GEX call/put walls / flip can later replace or augment VP nodes (see `poc_va_gex/v1_node_cloud`).

## Finds applied

- Primary rules choose SIDE; meta chooses WHETHER (PLAYBOOK locked architecture)
- Causal prior-window POC/VA only (no future profile leakage)
- Avoid raw price ML primary (`poc_va_xgb` failed)

## Finds avoided

- Predicting direction with XGB/LSTM on close
- Stacking more filters on WINNER without a new SIDE hypothesis

## Pass bar target

Must beat: PF ≥ 1.2, |DD| ≤ 25%, Sharpe ≥ 0.5, trades ≥ 40 on claimed window.
Compare OOS vs `v15_meta_xgb` / `v2_vwap` on the same holdout ranges (`runs/poc_va_antioverfit`).

## Kill criteria

If OOS fails → `tools/findings.py record --status fail --kind primary_rules` and follow `FAILURE_PROTOCOL.md`.
