# Multi-Regime Backtest Feasibility (P0-1)

**Question:** can v72_dual_sleeve be stress-tested against 2018+ regimes (2018 Q4,
2020 Feb–Apr, 2022) fully offline, per `docs/ML_PROD_READINESS_PLAN.md` P0-1?

**Answer: yes — already wired and executed once.** A 2018-01-01 → 2026-07-11
daily-bar run completes offline in ~9 s. Config:
`models/poc_va_macdha/v72_dual_sleeve/regime_stress_config.json`. Runner:
`tools/regime_backtest.py`. Results: `runs/v72_regime_probe/RESULTS.json`.

## What data exists locally

| Symbol | `data_cache/1d/` coverage | `data_cache/1h/` coverage |
|--------|---------------------------|---------------------------|
| TSLA, MU, SPY, XLP, QQQ | 2018-01-02 → 2026-07-10 (2141 bars) | 2024-07-11 → 2026-07-10 only |
| IONQ | 2021-01-04 → 2026-07-10 (listing) | 2024-07-11 → 2026-07-10 |
| APLD | 2022-04-13 → 2026-07-10 (listing) | 2024-07-11 → 2026-07-10 |

- **1H before 2024-07 does not exist locally** (and Yahoo hard-caps 1H history
  at ~730 days — same blocker `v13_long_oos` hit). A 2018 1H run would require
  a vendor download; **not** attempted (plan forbids large network pulls here).
- Daily bars are sufficient for the plan's purpose: regime behavior + drawdown
  containment, following the `v13_long_oos` Phase-A pattern (frozen rules,
  `interval=1D`, evaluate only, no retune).

## Plumbing note (why a loader shim is needed)

`source="local"` resolves symbols through `~/.vibe-trading/data-bridge/config.yaml`,
which pins every symbol to its **1h** parquet. Editing that machine-managed file
is invasive (other tooling rewrites it — see its `.bak-*` trail).
`tools/regime_backtest.py` instead patches the local loader in-process to read
`data_cache/1d/<SYM>.parquet` directly. No user config touched, no network.

## Caveats (read before quoting numbers)

1. **Not the promoted contract.** v71/v39d were selected on 1H bars; on 1D the
   same rule DNA trades differently. This is a *regime probe*, not a
   like-for-like backtest of the promoted book.
2. **Kill-switch throttles are not inside the backtest.** The risk_manager
   halts new entries at 18% DD and flattens at 28% — the raw probe drawdown
   overstates what a live book (with those gates) would have realized.
3. IONQ/APLD join at listing (2021/2022); early years trade a 5-name bag.

## First probe results (2026-07-16, `runs/v72_regime_probe/RESULTS.json`)

Full 2018→2026 1D run: **ret +119.2%, max DD −24.4%, Sharpe 0.59, n=197, WR 47.7%.**

| Stress window | Return | Max DD (within) | Bars active | Inside halt (18%) | Inside flatten (28%) |
|---|---|---|---|---|---|
| 2018 full year | +0.7% | −10.6% | 30% | yes | yes |
| 2018 Q4 (bear) | −0.4% | −0.9% | 9.5% | yes | yes |
| 2020 Feb–Apr (COVID) | +25.0% | −5.8% | 61% | yes | yes |
| 2022 full year (bear) | −4.1% | −17.7% | 67% | yes | yes |

Reading against the plan's bar ("may lose money in stress windows, but DD must
stay inside the kill-switch level and behavior must be explainable"):

- **2018 Q4**: essentially flat and mostly out of the market (9.5% of bars
  active) — the HTF/regime filters stand aside. Explainable, pass.
- **2020 Feb–Apr**: small DD, then long entries into the V-recovery. Pass.
- **2022**: loses −4.1% with −17.7% within-window DD — under the 18% halt level
  and well under 28% flatten. Borderline vs halt_new; the full-run max DD
  (−24.4%, hit across 2021→2022 peak-to-trough) **would have tripped halt_new
  (18%) live**, meaning risk would have been throttled before the bottom.
  Consistent with G7's instruction to size live risk to holdout-or-worse.
- Sharpe 0.59 across 2018–2026 vs 2.20 on the 2025–26 holdout is exactly the
  G1 concern quantified: the edge is regime-concentrated. This supports
  "signal-routing with manual review: yes / autonomous sizing: no".

## Exact commands

```bash
# Re-run the full probe (offline, ~9 s), writes runs/v72_regime_probe/RESULTS.json
.venv/bin/python tools/regime_backtest.py

# Custom window
.venv/bin/python tools/regime_backtest.py --start 2018-01-01 --end 2022-12-31

# Record the finding durably (models/_shared/findings.jsonl)
.venv/bin/python tools/findings.py record --model v72_dual_sleeve \
  --kind regime_stress --note "2018+ 1D probe: DD inside flatten level; 2022 loses -4.1%; edge regime-concentrated" \
  --metrics runs/v72_regime_probe/RESULTS.json
```

*(Check `tools/findings.py --help` for the exact record syntax before running
the last command.)*

## What's still missing / next steps

- **1H multi-year bars** would make this a like-for-like stress. Sources: LSE
  bulk export or a paid vendor — needs an explicit data-acquisition decision
  (network + possibly cost); do not do silently.
- **Gap-through-stop model** (fill at open, not stop price) from P0-2's text is
  partially covered by the engine's open-price fills; a dedicated worst-case
  gap model remains future work.
- Wire the kill-switch throttle into the backtest loop so stress DD reflects
  the live guard, not raw exposure.
