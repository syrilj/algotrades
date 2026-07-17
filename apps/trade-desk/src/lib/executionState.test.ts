import assert from "node:assert/strict";
import test from "node:test";

import {
  buildPaperOrder,
  decisionPresentation,
  feedPresentation,
  gammaDeskPresentation,
  gammaMethodology,
  gammaFreshness,
  isExecutionActionable,
  paperExecutionAllowed,
  ticketDisplayFromPlan,
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

  assert.equal(result.title, "Feed not ready for execution");
  assert.equal(result.eyebrow, "PAPER ORDER LOCKED");
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
  assert.equal(result.eyebrow, "PAPER ORDER LOCKED");
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
    decision: { analysis_action: "BUY NOW", mode: "EQUITY_HEDGE" },
  });

  assert.equal(result.title, "Signal cleared; order still blocked");
  assert.equal(result.eyebrow, "PAPER ORDER LOCKED");
  assert.match(result.detail, /BUY NOW/);
});

test("stand-aside execution still names the analysis setup so modes do not look contradictory", () => {
  const result = decisionPresentation({
    confidence: { state: "ABSTAIN", reasons: ["calibration_artifact_missing"] },
    ticket: { action: "abstain", mode: "STAND_ASIDE", vehicle: "none" },
    decision: { analysis_action: "WAIT", mode: "STAND_ASIDE" },
    model: { action_hint: "WAIT" },
  });

  assert.equal(result.eyebrow, "PAPER ORDER LOCKED");
  assert.match(result.detail, /WAIT/);
  assert.match(result.detail, /STAND_ASIDE/);
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

test("OI gamma uses snapshot time so delayed lastTradeDate does not hide squeeze", () => {
  const now = new Date("2026-07-15T21:00:00Z");
  const freshness = gammaFreshness(
    {
      // Chain last trade is hours old (normal for open interest).
      options_asof: "2026-07-15T16:00:00Z",
      // Snapshot was just computed.
      asof_utc: "2026-07-15T20:55:00Z",
      exposure_kind: "dealer_positioning_estimate",
    },
    now,
  );

  assert.equal(freshness.isCurrent, true);
  assert.equal(freshness.ageMinutes, 5);
  assert.equal(freshness.hasChainTimestamp, true);
  assert.ok((freshness.chainAgeMinutes ?? 0) >= 90);
});

test("Flow proxy gamma prefers options_asof and still ages out", () => {
  const now = new Date("2026-07-15T21:00:00Z");
  const stale = gammaFreshness(
    {
      options_asof: "2026-07-15T18:00:00Z",
      asof_utc: "2026-07-15T20:55:00Z",
      exposure_kind: "intraday_gamma_flow_proxy",
    },
    now,
  );
  assert.equal(stale.isCurrent, false);
  assert.equal(stale.ageMinutes, 180);

  const live = gammaFreshness(
    {
      options_asof: "2026-07-15T20:50:00Z",
      asof_utc: "2026-07-15T20:55:00Z",
      exposure_kind: "intraday_gamma_flow_proxy",
    },
    now,
  );
  assert.equal(live.isCurrent, true);
  assert.equal(live.ageMinutes, 10);
});

test("aged gamma snapshot still shows levels for analysis (does not hide board)", () => {
  const now = new Date("2026-07-15T21:00:00Z");
  const aged = gammaDeskPresentation(
    {
      options_asof: "2026-07-15T16:00:00Z",
      asof_utc: "2026-07-15T16:05:00Z",
      exposure_kind: "dealer_positioning_estimate",
    },
    now,
  );
  assert.equal(aged.hasSnapshot, true);
  assert.equal(aged.isStale, true);
  assert.equal(aged.isCurrent, false);
  assert.equal(aged.showLevels, true);
  assert.ok(aged.banner && /minutes old/i.test(aged.banner));
  assert.match(aged.banner ?? "", /stay visible|analysis/i);
  assert.equal(aged.ageMinutes, 295);
});

test("missing gamma timestamp still shows levels with honest unknown-age banner", () => {
  const view = gammaDeskPresentation({
    options_asof: null,
    asof_utc: null,
    exposure_kind: "dealer_positioning_estimate",
  });
  assert.equal(view.showLevels, true);
  assert.equal(view.isCurrent, false);
  assert.ok(view.banner && /unknown age|no usable snapshot time/i.test(view.banner));
});

test("current gamma snapshot shows levels without age banner", () => {
  const now = new Date("2026-07-15T21:00:00Z");
  const live = gammaDeskPresentation(
    {
      asof_utc: "2026-07-15T20:55:00Z",
      options_asof: "2026-07-15T16:00:00Z",
      exposure_kind: "dealer_positioning_estimate",
    },
    now,
  );
  assert.equal(live.showLevels, true);
  assert.equal(live.isCurrent, true);
  assert.equal(live.banner, null);
  assert.equal(live.sessionLabel, "live");
});

test("no gamma payload means no levels to show", () => {
  const empty = gammaDeskPresentation(null);
  assert.equal(empty.showLevels, false);
  assert.equal(empty.hasSnapshot, false);
});

/** Stand-aside plan shaped like live SPY abstain (max_loss 0, no model stop). */
function standAsidePlan() {
  return {
    ok: true,
    symbol: "SPY",
    account: 1000,
    live_ready: true,
    decision_support_ready: true,
    execution_readiness: { ready: false, blockers: ["setup_not_ready"] },
    live: {
      price: 594.8,
      go_long: false,
      go_short: false,
      freshness: { available: true, stale: false },
    },
    confidence: { state: "ABSTAIN", reasons: ["setup_not_ready"] },
    ticket: {
      action: "abstain",
      mode: "STAND_ASIDE",
      vehicle: "none",
      max_loss_dollars: 0,
      execution_blocked: true,
    },
    decision: { action: "abstain", mode: "STAND_ASIDE", analysis_action: "WAIT" },
    model: { model: "auto", entry: undefined, stop: undefined },
  };
}

test("stand-aside plan never gets a paper order (no invented shares)", () => {
  const plan = standAsidePlan();
  assert.equal(buildPaperOrder(plan), null);
  assert.equal(isExecutionActionable(plan), false);
  assert.equal(paperExecutionAllowed(plan), false);
});

test("ticketDisplayFromPlan does not invent stop, shares, or fake risk on abstain", () => {
  const plan = standAsidePlan();
  const view = ticketDisplayFromPlan(plan);

  assert.equal(view.executable, false);
  assert.equal(view.shares, null);
  assert.equal(view.dollarRisk, null);
  assert.equal(view.stop, null); // no model stop → null, not entry*0.95
  assert.equal(view.entry, 594.8); // live mark only
  assert.equal(view.maxLossBudget, 0); // backend truth, not account*0.02
  assert.equal(view.action, "abstain");
  // Critical: never force ≥1 share or non-zero planned risk when backend says 0
  assert.notEqual(view.shares, 1);
  assert.ok(view.dollarRisk == null || view.dollarRisk === 0);
});

test("ticketDisplayFromPlan does not invent stop when only entry/mark exists", () => {
  const plan = {
    ...standAsidePlan(),
    model: { model: "v39d", entry: 100, stop: undefined },
    live: {
      price: 100,
      go_long: true,
      go_short: false,
      freshness: { available: true, stale: false },
    },
  };
  const view = ticketDisplayFromPlan(plan);
  assert.equal(view.stop, null);
  assert.equal(view.shares, null);
  assert.equal(view.executable, false);
});

test("ticketDisplayFromPlan matches buildPaperOrder when fully gated", () => {
  const plan = {
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
  };
  const order = buildPaperOrder(plan);
  const view = ticketDisplayFromPlan(plan);
  assert.ok(order);
  assert.equal(view.executable, true);
  assert.equal(view.shares, order!.shares);
  assert.equal(view.dollarRisk, order!.dollarRisk);
  assert.equal(view.stop, 95);
  assert.equal(paperExecutionAllowed(plan), true);
});

test("max_loss_dollars 0 never sizes a paper order even with entry and stop", () => {
  const plan = {
    ok: true,
    live_ready: true,
    symbol: "SPY",
    account: 1000,
    decision_support_ready: true,
    execution_readiness: { ready: true },
    live: {
      price: 100,
      go_long: true,
      freshness: { available: true, stale: false },
    },
    confidence: { state: "ENTER" },
    ticket: { action: "enter", vehicle: "equity", max_loss_dollars: 0 },
    model: { model: "x", entry: 100, stop: 95 },
  };
  // isExecutionActionable requires positive max_loss
  assert.equal(isExecutionActionable(plan), false);
  assert.equal(buildPaperOrder(plan), null);
  const view = ticketDisplayFromPlan(plan);
  assert.equal(view.shares, null);
  assert.equal(view.maxLossBudget, 0);
  assert.equal(view.executable, false);
});
