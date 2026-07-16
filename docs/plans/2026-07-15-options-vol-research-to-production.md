# Options & Volatility Research-to-Production Program

**Date:** 2026-07-15  
**Status:** Phase 1 implemented (features + desk score); Phase 0/2 planned  
**Operating model:** AI-first — explicit contracts, eval gates, risk guardrails before model confidence  
**Related report:** Research-to-Production Program for Options and Volatility Trading Edges  
**Repo anchors:** `tools/options_*`, `tools/rv_har.py`, `tools/features_vrp.py`, `tools/vol_package_score.py`, `models/poc_va_macdha/*opts*`, OptionsDesk

---

## 1. Objective

Build a **factory for pricing residuals and hedged trade packages**, not free-form strike predictors.

| Goal | Non-goal |
|------|----------|
| Matched-horizon IV vs RV features | Millisecond OPRA microstructure first |
| Package scores with cost/liquidity gates | Auto-promote synthetic opts models to live |
| Desk surfaces directional **and** vol-package modes | RL over full chain action space |
| Walk-forward + multiple-testing before promotion | Full-window vanity Sharpe |

---

## 2. Contracts (stable interfaces)

### 2.1 Feature row (`features_vrp`)

```json
{
  "symbol": "SPY",
  "asof": "2026-07-15T00:00:00Z",
  "spot": 580.1,
  "rv_har_21d_ann": 0.14,
  "rv_har_5d_ann": 0.18,
  "atm_iv": 0.16,
  "iv_rv_spread": 0.02,
  "term_slope": 0.01,
  "skew_25d": -0.04,
  "near_dte": 21,
  "next_dte": 49,
  "data_quality": "ok|partial|degraded"
}
```

### 2.2 Vol package score (`vol_package_score`)

```json
{
  "ok": true,
  "symbol": "SPY",
  "features": { "...": "features_vrp row" },
  "packages": [
    {
      "template": "delta_neutral_long_vol",
      "score": 0.42,
      "edge_after_cost_proxy": 0.01,
      "action": "consider|stand_aside|avoid",
      "reasons": ["iv_rv_spread > 0 but thin; research only"]
    }
  ],
  "recommended": {
    "template": "stand_aside",
    "action": "stand_aside",
    "score": 0.0,
    "reasons": ["..."]
  },
  "guardrails": {
    "max_risk_pct": 0.18,
    "research_only": true,
    "auto_trade": false
  },
  "asof_utc": "..."
}
```

**Invariant:** `auto_trade` is always `false` until Phase 2 package backtests pass promotion gates.

### 2.3 Options plan desk extension

`OptionsPlanResponse.vol_package` optional field — same shape as §2.2. Failure must not block directional structure (partial OK).

---

## 3. Phases, files, acceptance criteria

### Phase 0 — Chain warehouse (planned)

| Deliverable | Path | Acceptance |
|-------------|------|------------|
| Schema + write path | `data_cache/options/<interval>/<symbol>.parquet` | Point-in-time chain rows; no future leaks |
| Manifest | `data_cache/options/MANIFEST.json` | Checksums + asof range |
| QA script | `tools/options_chain_qa.py` | Parity/cross/zero-OI report |

**Exit:** any day-T signal regenerates the same contract set.

### Phase 1 — Surface + RV + IV–RV (this sprint)

| Deliverable | Path | Acceptance |
|-------------|------|------------|
| HAR-RV | `tools/rv_har.py` | Unit tests; SPY/QQQ from `data_cache/1d` |
| Surface snapshot | `tools/options_surface.py` | ATM IV, term slope, skew proxy; yfinance live + graceful degrade |
| Feature join | `tools/features_vrp.py` | Combined row + optional parquet out |
| Package scorer | `tools/vol_package_score.py` | `--json` CLI; deterministic rules |
| Tests | `tests/test_options_vol_features.py` | Synthetic bars + mocked surface |
| Desk wire | OptionsDesk + `options-plan` | Shows vol package panel; does not gate buy on scorer alone |

**Exit:** operator can run:

```bash
.venv/bin/python tools/vol_package_score.py --symbol SPY --json
```

and see IV–RV + package actions.

### Phase 2 — Package library backtests (next)

| Package | Engine | Gates |
|---------|--------|-------|
| Delta-hedged ATM straddle (IV–RV) | extend `options_portfolio` | min n≥30, net Sharpe OOS, cost grid |
| Calendar roll-down | same | vs term-slope signal |
| Debit directional (existing) | `*_opts` + picker | keep OPTIONS_WINNER discipline |

**Promotion gates (draft):**

```json
{
  "min_trades": 30,
  "min_oos_sharpe": 0.8,
  "max_oos_dd": -0.25,
  "min_edge_after_half_spread": 0.0,
  "require_pbo_below": 0.5,
  "auto_promote": false
}
```

### Phase 3 — Ranker + paper (later)

- Supervised rank among **predefined templates only**
- Paper ledger + live-vs-backtest slippage
- Kill switch + Greek caps independent of model score

---

## 4. Risk & AI-first controls

1. **Hard caps beat model confidence** — size/Greeks/open options count.
2. **Immutable experiment artifacts** under `runs/options_vrp_*`.
3. **No silent empty surfaces** — `data_quality=degraded` + reasons.
4. **Eval first** — unit tests for features; package PnL eval before UI “attack”.
5. **Partial failure** — vol score fail does not break directional options plan.

---

## 5. Ownership map

| Layer | Owner module |
|-------|----------------|
| Equity timing | `v72_dual_sleeve` / live_plan |
| Directional options structure | `options_picker` + OPTIONS_WINNER |
| Vol relative-value features | `rv_har` + `options_surface` + `features_vrp` |
| Package recommendation (research) | `vol_package_score` |
| Desk UX | `OptionsDesk` / `api/options-plan` |

---

## 6. Explicit non-promotions

See `docs/plans/2026-07-15-options-models-audit.md`.
