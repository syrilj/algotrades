# v28_feedback_opts (generation 2 — **full-window research peak, NOT OOS default**)

> **Promotion status (2026-07-12):** Wins full-window feedback loop (+104%) but **loses pure OOS aggregate** to `v22_opts_live`.  
> Live / OPTIONS default → **`v22_opts_live`**. See `OPTIONS_WINNER.json` + `runs/poc_va_oos_rank/FINDINGS.md`.

## Feedback-loop result (full window 2024-08-01 → 2026-07-11)

| Variant | Return | Max DD | Sharpe | WR | Notes |
|---------|--------|--------|--------|-----|-------|
| **v28 surgical + 10d cooloff** | **+104.1%** | **−11.2%** | **1.40** | 80% | **WINNER** |
| baseline v27 conf | +81.4% | −12.2% | 1.25 | 82% | prior champ |
| surgical FOMC∧VIX only | +74.5% | −15.5% | 1.17 | 75% | skips Dec-18 MU but takes IONQ double-tap |
| broad narrative | +65.2% | −17.5% | 1.09 | 75% | cut winners |
| event_vix (FOMC/CPI/NFP) | +31.9% | −9.3% | 0.78 | 86% | too much capacity kill |

`beats_baseline=True` (Δret **+22.7pp**, slightly better DD).

## Failure autopsy → policy

From **v27** roundtrips (11 closed, 2 losses):

| Loss | Date | PnL | Narrative | Fix |
|------|------|-----|-----------|-----|
| MU | 2024-12-18 | −71k | `FED_EVENT+FEAR_VOL+RATES_UP` FOMC day | **Surgical**: block only `fomc_day ∧ vix_elevated` |
| MU | 2024-11-25 | −60k | `RISK_ON_QUIET` | Not macro — cooloff doesn't prevent first loss |

### Why surgical alone underperformed

Skipping Dec-18 MU free cash for 2025, but then:

1. IONQ 2025-02-05 → −50k  
2. IONQ 2025-02-10 re-entry → −90k  

### Why cooloff wins

After IONQ Feb-6 loss, **10d cooloff** blocks the second IONQ entry and the stack takes **HOOD 2025-02-11 (+174k)** plus later MU winners.

Also: broad FEAR/near-FOMC size-down cut winners (AVGO near FOMC, MU under FEAR_VOL) — **do not use broad mode live**.

## Promoted defaults (`hunt_config.json`)

```json
{
  "narrative_mode": "surgical",
  "loss_cooloff_days": 10,
  "use_conf_tier": true,
  "dte_days": 14,
  "risk_pct": 0.10
}
```

## Econ / calendar data used

`tools/econ_narrative.py`:

- VIX vs 20d MA, TNX 5d, QQQ vs 50d  
- FOMC + CPI + NFP public calendars  
- Modes: `surgical` | `fomc_day` | `event_vix` | `broad` | `off`

## Re-run loop

```bash
.venv/bin/python tools/feedback_loop_opts.py
```

Artifacts:

- `runs/poc_va_feedback_loop/LOOP_STATE.json`
- `runs/poc_va_feedback_loop/FAILURE_AUTOPSY.md`
- Winner run: `runs/poc_va_feedback_loop/v28_surgical_plus_cooloff/`
