# Version README — v19_node_cloud

- **Family / version:** `poc_va_macdha` / `v19_node_cloud`
- **Parent / copied from:** conceptual fork of `v2_vwap` levels + new MA-cloud targeting (not a filter stack on WINNER)
- **Hypothesis:** see `HYPOTHESIS.md`
- **Engine:** `signal_engine.py`
- **Config window:** see `config.json` (default 2024-08 → 2026-07)
- **Results:** `results.json` (pending first backtest)
- **Finding recorded:** no
- **Status:** explore

## Idea (one line)

**Nodes = magnets · MA cloud = compass · trade the path, don’t predict the destination.**

## Rules sketch

1. Build prior-window VAL / POC / VAH nodes.
2. Build EMA cloud (fast / mid / slow). Bullish when fast > mid > slow and close ≥ mid.
3. Target = nearest node **above** spot when bullish (else no long).
4. Enter long when bullish cloud + close holds above a support node (VAL or POC) + target is meaningfully above spot.
5. Exit when close reaches target, cloud flips, or support node is lost.

## Live GEX extension

`models/poc_va_gex/v1_node_cloud/` — same compass, nodes from call_wall / put_wall / flip when chain is available.
