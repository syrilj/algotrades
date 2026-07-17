# ML Production Readiness — Assessment & Improvement Plan

**Scope:** `poc_va_macdha` equity book, promoted model `v72_dual_sleeve`, served via `services/market_runtime` + `tools/live_plan.py`.
**Date:** 2026-07-16 · **Evidence:** `DEPLOYMENT_MANIFEST.json`, `runs/v72_dual_sleeve/{STATE,COMPARE}.json`, `runs/calibration/active/v72_dual_sleeve.json`, test suite (367 passed).

---

## Verdict

| Question | Answer |
|---|---|
| Is the *engineering* done right? | **Largely yes.** Pinned artifacts, fail-closed fallbacks, locked holdout, inert broker drafts, shadow ledger, honest calibration gating. |
| Is the *edge* statistically proven? | **Not yet.** One bull regime (2024–2026), 84 holdout trades, ~80 model versions searched over the same data, optimistic cost model. |
| Can it go live? | **Signal-routing with manual review: yes** (what the manifest already permits). **Probability-sized autonomous execution: no** — correctly blocked; keep it blocked until the gates below pass. |

---

## What is already done right (keep it)

1. **Deployment manifest** — SHA256-pinned bundle, ordered fail-closed fallbacks (`v39d_confluence → v71 → v39b`), explicit rollback model.
2. **Locked holdout** — train 2024-08→2025-08, holdout 2025-08→2026-07-11; merge rule pre-registered; no post-holdout retune claimed and consistent with artifacts.
3. **Honest calibration** — isotonic calibrator *rejected* because OOS reliability got worse; identity map shipped with `probability_calibrated: false` and "ordinal, not probability" semantics; probability sizing blocked in `execution_readiness`.
4. **Fail-closed execution** — blocked readiness ⇒ `side=FLAT, qty=0, transmit_allowed=false`; options can never emit an equity draft; recent-loss and drawdown throttles reduce risk before halt (all covered by tests).
5. **Shadow decision ledger** — settlement only from recorded reference prices, never inferred; corrupt-tail tolerant.
6. **Causal integrity tests** — prefix invariance and symbol-order independence (lookahead guard) pass.
7. **Test suite** — 367 tests green in ~13 s.

---

## Gap analysis

| # | Gap | Severity | Evidence |
|---|-----|----------|----------|
| G1 | **Single-regime data.** All windows sit inside 2024-08→2026-07; universe is 7 high-beta long-only names that rallied in exactly this era. No 2018/2020/2022 stress. | **Critical** | `data_contract` in manifest |
| G2 | **Selection pressure vs. sample size.** ~80 versions explored on the same era; holdout Sharpe 2.20 on n=84 trades has a wide confidence interval and no multiple-testing correction (deflated Sharpe / SPA). Components v71 & v39d were themselves chosen with knowledge of this data. | **Critical** | `models/poc_va_macdha/` version tree, `STATE.json` |
| G3 | **Top-bin anti-calibration.** Final-holdout reliability: predicted ~0.90 bin realized **0.25** (n=4); ECE 0.199 on n=37. Highest-confidence signals are currently the least trustworthy tail. | **High** | `runs/calibration/active/v72_dual_sleeve.json` |
| G4 | **Cost realism.** Flat `commission: 0.001`, no spread/slippage model, fills at 1H bar close. IONQ/APLD spreads and overnight gaps through stops are unmodeled. | **High** | `v72_dual_sleeve/config.json` |
| G5 | **Calibrator data starvation.** 152 OOF rows / 37 holdout rows — too few to fit a non-identity calibrator that can pass the gates. This is the blocker the manifest names. | **High** | calibration artifact `dataset` |
| G6 | **No automated live-vs-backtest degradation rule.** Shadow ledger + monitoring metrics exist, but no codified "live expectancy breaches band ⇒ auto-demote to `rollback_model`" policy. | **Medium** | `tools/model_monitoring.py`, tests |
| G7 | **Train→holdout decay.** Sharpe 3.60→2.20, WR 73%→65%, DD −11%→−20%. Normal, but size live risk to holdout (or worse), not full-window, numbers. | **Medium** | `COMPARE.json` |

---

## Improvement plan

### P0 — before any live capital (1–2 weeks)

1. **Multi-regime stress backtest (G1).**
   - Extend to 2018-01-01 on daily bars where 1H is unavailable (the `v13_long_oos` harness already does this pattern).
   - Mandatory sub-windows: 2018 Q4, 2020 Feb–Apr, 2022 full year.
   - Pass bar: strategy may lose money in stress windows, but max DD must stay inside the live kill-switch level and behavior must be explainable (e.g., flat because HTF filter is red). Record via `tools/findings.py`.
2. **Cost & slippage stress (G4).**
   - Re-run train/holdout at 2× commission + per-symbol spread haircut (thin names ≥ 2× SPY’s), and a gap-through-stop model (fill at open, not stop price).
   - Pass bar: holdout return stays positive and Sharpe ≥ 1.0 under stress.
3. **Selection-bias accounting (G2).**
   - Compute **Deflated Sharpe Ratio** on the holdout using the true number of trials (count versions in `TRAINING_LEADERBOARD.json` + version tree, not just the 4 in `COMPARE.json`).
   - Pass bar: DSR > 0.95 probability that true Sharpe > 0. If it fails, the honest reading is "promising, unproven" — stay in shadow mode longer rather than adding filters.
4. **Confidence cap (G3).**
   - Until a real calibrator ships, clamp displayed/live confidence at the highest bin with adequate support (~0.75). Do not let UI or sizing ever consume the 0.85–0.95 range the model currently emits.
5. **Codify the demotion rule (G6).**
   - Write `tools/live_guard.py` (or extend model_monitoring): daily job settles shadow ledger, computes rolling 20-trade WR and mean realized R, compares against holdout-derived bands (e.g., bootstrap p05).
   - Breach ⇒ flip manifest `active` to `rollback_model` and set `execution_readiness.model_routing: "blocked"`. Test it the same way `test_live_trading_safety.py` tests drafts.

### P1 — first month live (shadow → small size)

6. **Paper/shadow gate (G2, G7).**
   - ≥ 4 weeks or ≥ 30 settled ENTER decisions in the shadow ledger at zero size.
   - Promote to small live size only if realized WR and mean R fall inside the holdout bootstrap band. Pre-register these thresholds in the manifest *before* the shadow period starts.
7. **Grow the calibration dataset (G5).**
   - Every shadow/live decision (ENTER *and* WATCH) feeds the OOF pool. Target ≥ 400 rows.
   - Then refit cross-fitted isotonic/Platt with the existing embargoed 5-fold harness; ship only if OOS reliability beats raw (the existing gate). This unblocks probability-sized execution properly.
8. **Execution parity monitoring.**
   - Log intended fill (bar close) vs. actual fill per trade; alert when realized slippage exceeds the stress assumption from P0-2.

### P2 — scale-up (after live evidence)

9. **XGB meta-filter as ranker, not gate** — the `IMPROVE_ML_BACKTEST.md` path: label rule-generated candidates, walk-forward XGB, SHAP-pruned features; promote only on OOS PF/DD improvement. This also becomes the natural non-identity calibrator input.
10. **Universe & capacity** — add liquid beta names (AAPL, NVDA, META, IWM) as a separate bucket so results aren't hostage to the 2024–26 high-beta rally; measure per-symbol capacity before sizing up.
11. **Short sleeve / regime router** — only after the long book has live evidence; mirror rules exist in the registry notes.

---

## Go-live checklist (all must be true)

- [ ] Multi-regime backtest recorded; DD inside kill-switch in 2020/2022 windows
- [ ] 2× cost + slippage stress: holdout still positive, Sharpe ≥ 1.0
- [ ] Deflated Sharpe accounting for full search count is positive
- [ ] Confidence clamped to supported bins; UI shows "ordinal, not probability"
- [ ] Auto-demotion rule implemented + tested (manifest flips to rollback on breach)
- [ ] ≥ 4 weeks / ≥ 30 settled shadow decisions inside expectancy bands
- [ ] Alerting on data staleness (supervisor freshness → execution gate) verified end-to-end
- [ ] Kill-switch drill performed: force a breach, confirm system goes FLAT/blocked

## Anti-patterns to refuse (already in FAILURE_PROTOCOL, restated)

- No retuning on the locked holdout; a failed gate means more shadow time, not a new filter.
- No stacking hard filters to chase win rate (v29/v30 lesson — WR without PF/DD is vanity).
- Never treat `last_confidence` as a probability until a cross-fitted non-identity calibrator passes the reliability gate.

---

*This is an engineering-readiness assessment of the system, not investment advice; live results depend on regime and execution beyond what any backtest shows.*
