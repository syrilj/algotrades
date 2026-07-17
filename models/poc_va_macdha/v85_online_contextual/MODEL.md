# v85_online_contextual

Research-only online contextual challenger. It routes three frozen signal
experts—v72-equivalent DUAL, causal-fixed v39d CORE, and v71-equivalent
SNIPER—plus CASH. The online update uses only matured next-open returns and
charges entry, resize, and exit turnover.

Safety contract:

- Frozen dependency hashes are verified before loading.
- Expert ownership is locked until that expert exits.
- Stress/high-volatility context can only reduce an open episode.
- Stale or incomplete cross-asset context blocks new entries.
- Options snapshots are activity-only; no bullish/bearish side is inferred.
- `last_confidence` is ordinal expert support, never a win probability.
- Historical calls use deterministic full-window replay. Live promotion is
  blocked until a versioned, exactly-once persisted state path passes restart
  parity and the model completes a no-retune forward-paper window.

This model is intentionally not listed in `DESK_ROUTING.json` or the deployment
manifest. Historical results are evidence for research selection, not a fresh
holdout, because the repository has no untouched validation period remaining.
