# quantmodel data

- `raw/demo` — optional exported synthetic snapshots  
- `processed/` — intermediate feature tables  
- `metadata/` — vendor docs  
- `manifests/` — hashed data manifests  

Primary live research data is loaded from the monorepo `data_cache/` (LSE) via `data.vendor: lse_cache`.

**Never backtest only today’s survivors for deployment decisions.** Synthetic vendor exists for engine correctness; connect Norgate/Polygon for research-grade PIT history.
