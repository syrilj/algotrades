import assert from "node:assert/strict";
import test from "node:test";

import {
  buildPaperOrder,
  decisionPresentation,
  feedPresentation,
  gammaMethodology,
  gammaFreshness,
  isExecutionActionable,
} from "./executionState.ts";

test("closed-market latest session data is usable and explicitly labeled", () => {
  const result = feedPresentation({
    available: true,
    stale: false,
    market_session: "closed",
    freshness_basis: "latest_completed_session",
  });

  assert.equal(result.canUse, true);
  assert.equal(result.label, "Latest session close");
  assert.equal(result.tone, "closed-current");
});

test("stale data fails closed", () => {
  const result = feedPresentation({
    available: true,
    stale: true,
    market_session: "open",
  });

  assert.equal(result.canUse, false);
  assert.equal(result.label, "Stale — do not execute");
  assert.equal(result.tone, "blocked");
});

test("execution is actionable only when confidence, decision, and data all pass", () => {
  const plan = {
    ok: true,
    live_ready: true,
    account: 10_000,
    decision_support_ready: true,
    execution_readiness: { ready: true },
    live: { price: 100, freshness: { available: true, stale: false } },
    confidence: { state: "ENTER" },
    ticket: { action: "enter", vehicle: "equity", max_loss_dollars: 120 },
    model: { entry: 101, stop: 95 },
  };

  assert.equal(isExecutionActionable(plan), true);
  assert.equal(
    isExecutionActionable({ ...plan, confidence: { state: "ABSTAIN" } }),
    false,
  );
  assert.equal(
    isExecutionActionable({
      ...plan,
      live: { price: 100, freshness: { available: true, stale: true } },
    }),
    false,
  );
  assert.equal(
    isExecutionActionable({
      ...plan,
      gex: { spot: 125, price_consistent: false },
    }),
    false,
  );
});

test("decision copy makes an abstention unambiguously non-actionable", () => {
  const result = decisionPresentation({
    confidence: {
      state: "ABSTAIN",
      reasons: ["market_data_stale_or_unavailable"],
    },
    ticket: { action: "abstain", mode: "STAND_ASIDE" },
  });

  assert.equal(result.title, "Stand aside");
  assert.equal(result.eyebrow, "NO TRADE");
  assert.match(result.detail, /fresh market data/i);
});

test("ENTER confidence alone never claims Ready to execute", () => {
  // Confidence + ticket say enter, but feed is stale and readiness failed —
  // operator must not see a false "SETUP READY" claim.
  const result = decisionPresentation({
    ok: true,
    live_ready: true,
    account: 10_000,
    decision_support_ready: true,
    execution_readiness: { ready: false, blockers: ["fresh_market_data"] },
    live: { price: 100, freshness: { available: true, stale: true } },
    confidence: { state: "ENTER" },
    ticket: { action: "enter", vehicle: "equity", max_loss_dollars: 120 },
    model: { entry: 101, stop: 95 },
  });

  assert.notEqual(result.eyebrow, "SETUP READY");
  assert.notEqual(result.title, "Ready to execute");
  assert.equal(result.eyebrow, "NO TRADE");
});

test("full gate pass presents Ready to execute", () => {
  const plan = {
    ok: true,
    live_ready: true,
    account: 10_000,
    decision_support_ready: true,
    execution_readiness: { ready: true },
    live: { price: 100, go_long: true, freshness: { available: true, stale: false } },
    confidence: { state: "ENTER" },
    ticket: { action: "enter", vehicle: "equity", max_loss_dollars: 120 },
    model: { entry: 101, stop: 95 },
  };
  const result = decisionPresentation(plan);
  assert.equal(result.eyebrow, "SETUP READY");
  assert.equal(result.title, "Ready to execute");
  assert.equal(isExecutionActionable(plan), true);
});

test("passed signal still shows blocked when execution readiness fails", () => {
  const result = decisionPresentation({
    confidence: { state: "ENTER" },
    execution_readiness: { ready: false, blockers: ["portfolio_state_verified"] },
    ticket: { action: "abstain", vehicle: "equity" },
  });

  assert.equal(result.title, "Execution checks blocked this plan");
  assert.equal(result.eyebrow, "NO TRADE");
});

test("paper order size is derived from the actual stop risk", () => {
  const order = buildPaperOrder({
    ok: true,
    live_ready: true,
    symbol: "APLD",
    account: 1000,
    decision_support_ready: true,
    execution_readiness: { ready: true },
    live: {
      price: 100,
      go_long: true,
      freshness: { available: true, stale: false },
    },
    confidence: { state: "ENTER" },
    ticket: { action: "enter", vehicle: "equity", max_loss_dollars: 120 },
    model: { model: "v39d_confluence", entry: 101, stop: 95 },
  });

  assert.deepEqual(order, {
    symbol: "APLD",
    side: "long",
    shares: 9,
    entry: 101,
    stop: 95,
    dollarRisk: 54,
    model: "v39d_confluence",
    account: 1000,
  });
});

test("options decisions can never be converted into stock paper orders", () => {
  const order = buildPaperOrder({
    ok: true,
    live_ready: true,
    symbol: "APLD",
    account: 1000,
    decision_support_ready: true,
    execution_readiness: { ready: true },
    live: {
      price: 100,
      go_long: true,
      freshness: { available: true, stale: false },
    },
    confidence: { state: "ENTER" },
    ticket: { action: "enter", vehicle: "options", max_loss_dollars: 220 },
    model: { model: "v39d_confluence", entry: 101, stop: 95 },
  });

  assert.equal(order, null);
});

test("stop must be on the loss side of the entry", () => {
  const order = buildPaperOrder({
    ok: true,
    live_ready: true,
    symbol: "APLD",
    account: 1000,
    decision_support_ready: true,
    execution_readiness: { ready: true },
    live: {
      price: 100,
      go_long: true,
      freshness: { available: true, stale: false },
    },
    confidence: { state: "ENTER" },
    ticket: { action: "enter", vehicle: "equity", max_loss_dollars: 20 },
    model: { model: "v39d_confluence", entry: 100, stop: 105 },
  });

  assert.equal(order, null);
});

test("Gamma methodology never calls volume flow dealer inventory", () => {
  assert.equal(
    gammaMethodology({ exposure_kind: "intraday_gamma_flow_proxy" }).label,
    "Intraday gamma-flow proxy",
  );
  assert.equal(
    gammaMethodology({ exposure_kind: "dealer_positioning_estimate" }).label,
    "Dealer positioning estimate",
  );
});

test("Gamma levels expire after ninety minutes, not ninety hours", () => {
  const freshness = gammaFreshness(
    "2026-07-14T20:00:00Z",
    new Date("2026-07-14T22:00:00Z"),
  );

  assert.equal(freshness.isCurrent, false);
  assert.equal(freshness.ageMinutes, 120);
});
