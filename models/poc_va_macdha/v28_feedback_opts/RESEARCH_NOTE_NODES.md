# Research note — nodes return as selectivity, not primary replacement

## v19 pure node+cloud primary: FAIL
- Run: `runs/poc_va_v19_node_cloud` / `v19_node_cloud/results.json`
- Result: −38% return, DD −68%, Sharpe −0.12, n=374 (too active, wrong locations)
- Lesson: **do not replace** specialist St.MACD-HA primary with bare node/cloud loop

## Correct use of nodes
- **Nodes** (VAL/POC/VAH) = magnets — only engage where market is defending/breaking through
- **EMA cloud** = compass — which node is price traveling toward
- **St.MACD-HA** (HTF) = trend regime; local OB/OS zones for chase avoidance / reclaim prefer
- Fuse as **selectivity gate on top of v21 specialists**, then v28 options risk

## v28 full-window baseline (keep)
- +104.1%, DD −11.2%, Sharpe 1.40, n=30
- Surgical macro + 10d cooloff + conf tier + 14 DTE

## Next
- `v31_selective_nodes_opts`: selective structure gate + soft secondary size
