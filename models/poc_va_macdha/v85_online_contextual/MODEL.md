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
- Historical calls use deterministic full-window replay. The market runtime's
  `AdaptiveReplayStore` provides a versioned, exactly-once completed-bar ledger;
  restart/idempotency parity is covered by tests. Live promotion remains blocked
  until that path is explicitly enabled and a no-retune forward-paper window is
  complete.

This model is intentionally not listed in `DESK_ROUTING.json` or the deployment
manifest. Historical results are evidence for research selection, not a fresh
holdout, because the repository has no untouched validation period remaining.

Corrected causal benchmark (`source=local`, 1H, $1,000, 5 bp slippage and 5 bp
commission): full +344.6% return / -17.7% max drawdown / 2.834 Sharpe; later
2025-08-01 through 2026-07-11 +60.5% / -15.5% / 2.026. Closed-episode win
rates are 73.5% (114/155, Wilson 95% 66.1%-79.9%) full and 62.3% (48/77,
51.2%-72.3%) later. These intervals do not support an 80%-90% probability
claim. See `runs/v85_online_contextual/LEADERBOARD.md` for the same-contract
comparison with v39d, v71, v72, and v81.
