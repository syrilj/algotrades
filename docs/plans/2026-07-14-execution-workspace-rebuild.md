# Execution Workspace Rebuild Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task.

**Goal:** Make the Execution workspace safe and understandable for live trading by unifying its workflow, fixing feed consistency and freshness, and clearly separating actionable decisions from research-only Gamma/options evidence.

**Architecture:** `tools/live_plan.py` becomes the source of truth for a price-consistent live snapshot and market-session-aware freshness. `tools/gamma_exposure.py` rejects inconsistent option-chain underlying prices and labels OI-based dealer positioning separately from volume-based flow proxies. A new `ExecutionDesk` client component owns shared symbol/account state and renders a guided Discover → Verify → Decide → Execute workflow; the existing Watch, Options, and Gamma desks remain available as shared-context detail views.

**Tech Stack:** Python 3.13, pandas, pytest, Next.js 15, React 19, TypeScript, Node test runner, Tailwind/global CSS, local paper-ledger API.

---

### Task 1: Lock the live-data contract with failing tests

**Files:**
- Create: `tests/test_live_execution_data.py`
- Modify: `tests/test_confidence_calibration.py`
- Test: `tests/test_gamma_flip.py`

**Steps:**

1. Add a test proving LSE candle requests receive `YYYY-MM-DD`, not an ISO timestamp.
2. Add a test proving a completed regular-session bar remains usable overnight until the next session begins.
3. Add a test proving an option-chain underlying price that materially disagrees with the live candle price is rejected.
4. Add a test proving standard GEX is `gamma × contracts × 100 × spot² × 0.01` and the unit is dollars per 1% move.
5. Run the focused tests and verify each new behavior fails for the expected reason.

Run: `.venv/bin/python -m pytest tests/test_live_execution_data.py tests/test_confidence_calibration.py tests/test_gamma_flip.py -q`

### Task 2: Repair feed selection, freshness, and Gamma trust

**Files:**
- Modify: `tools/live_plan.py`
- Modify: `tools/confidence_runtime.py`
- Modify: `tools/gamma_exposure.py`
- Modify: `apps/trade-desk/src/lib/types.ts`

**Steps:**

1. Format LSE start dates as `YYYY-MM-DD` in intraday and daily requests.
2. Attach `source`, `market_session`, `timestamp`, and freshness metadata to the live snapshot.
3. Make freshness session-aware: strict while the US market is open, but accept the latest completed regular-session bar overnight/weekends until the next open.
4. Compare the LSE option-chain underlying to the trusted candle spot; reject/fallback when divergence exceeds the configured tolerance.
5. Preserve the standard GEX calculation while returning methodology fields: `exposure_kind`, `weight`, `formula`, `sign_assumption`, `price_consistent`, and warnings.
6. Run focused tests until green, then run the broader confidence/Gamma test group.

### Task 3: Add testable Execution presentation rules

**Files:**
- Create: `apps/trade-desk/src/lib/executionState.ts`
- Create: `apps/trade-desk/src/lib/executionState.test.ts`

**Steps:**

1. Add failing Node tests for feed-state labels, actionable gating, plain-language decision copy, and hiding execution controls on ABSTAIN/WATCH/stale data.
2. Run the tests and confirm RED.
3. Implement the smallest pure helpers needed by the tests.
4. Re-run and confirm GREEN.

Run: `node --experimental-strip-types --test src/lib/executionState.test.ts`

### Task 4: Build the unified guided Execution workspace

**Files:**
- Create: `apps/trade-desk/src/components/live/ExecutionDesk.tsx`
- Modify: `apps/trade-desk/src/app/live/page.tsx`
- Modify: `apps/trade-desk/src/components/live/LiveDesk.tsx`
- Modify: `apps/trade-desk/src/components/gamma/GammaExposureDesk.tsx`
- Modify: `apps/trade-desk/src/components/options/OptionsDesk.tsx`
- Modify: `apps/trade-desk/src/components/analyze/TradeButton.tsx`
- Modify: `apps/trade-desk/src/app/globals.css`

**Steps:**

1. Replace the default Ticket form with a guided command strip: symbol, account, Analyze, and Scan Market.
2. Add a persistent data-trust rail showing source, timestamp, session, freshness, and cross-source agreement.
3. Render one primary decision card with plain language: Enter, Watch, or Stand aside.
4. Show size, entry, stop, max loss, and paper execution only when the data and confidence gates are actionable.
5. Hide irrelevant exit rules for stand-aside decisions; explain exactly what must change instead.
6. Keep Watch, Options, and Gamma as detailed secondary tabs and preserve symbol/account in their URLs.
7. Label Gamma as `dealer positioning estimate` for OI or `intraday gamma-flow proxy` for volume; never present the latter as known dealer inventory.
8. Add responsive industrial/operator styling with a compact hierarchy and visible focus states.

### Task 5: Verify the complete user journey

**Files:**
- Modify only if verification finds a confirmed defect.

**Steps:**

1. Run Python focused and full relevant tests.
2. Run Node presentation-rule tests.
3. Run TypeScript compilation and the production Next.js build.
4. Use the local browser to verify desktop and narrow layouts for: empty state, successful plan, stale/unavailable state, Watch, Options, Gamma, and paper-trade gating.
5. Call the live-plan and Gamma APIs for APLD and verify prices agree or Gamma fails closed with a visible warning.
6. Review `git diff` to ensure unrelated user changes remain untouched.

Verification commands:

```bash
.venv/bin/python -m pytest tests/test_live_execution_data.py tests/test_confidence_calibration.py tests/test_gamma_flip.py -q
/Users/syriljacob/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --experimental-strip-types --test src/lib/executionState.test.ts
/Users/syriljacob/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node node_modules/typescript/bin/tsc --noEmit
/Users/syriljacob/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node node_modules/next/dist/bin/next build
```
