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
    decision_support_ready: true,
    live: { price: 100, freshness: { available: true, stale: false } },
    confidence: { state: "ENTER" },
    ticket: { action: "enter", max_loss_dollars: 120 },
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

test("paper order size is derived from the actual stop risk", () => {
  const order = buildPaperOrder({
    ok: true,
    symbol: "APLD",
    account: 1000,
    decision_support_ready: true,
    live: {
      price: 100,
      go_long: true,
      freshness: { available: true, stale: false },
    },
    confidence: { state: "ENTER" },
    ticket: { action: "enter", max_loss_dollars: 120 },
    model: { model: "v39d_confluence", entry: 101, stop: 95 },
  });

  assert.deepEqual(order, {
    symbol: "APLD",
    side: "long",
    shares: 20,
    entry: 101,
    stop: 95,
    dollarRisk: 120,
    model: "v39d_confluence",
    account: 1000,
  });
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
