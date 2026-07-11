# Hypothesis — poc_va_gex / v1_node_cloud

**Date:** 2026-07-11

## Claim

Live desk layer: **GEX walls + flip are the nodes**; an **MA cloud** is the compass that picks which node spot is traveling toward. Output is a **guide** (target node, room %, regime) — not a price prediction. Stock primary SIDE for backtests lives in `poc_va_macdha/v19_node_cloud` (VP nodes, fully historical). This folder is the options-aware live overlay.

## Usage

```bash
.venv/bin/python models/poc_va_gex/v1_node_cloud/node_cloud_guide.py --ticker TSLA
```

## Kill criteria

If live guides disagree with OOS `v19_node_cloud` behavior in a way that adds noise without lift → keep as research-only; do not wire into meta size until walk-forward proves lift.
