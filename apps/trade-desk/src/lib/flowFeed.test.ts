import assert from "node:assert/strict";

import { mergeFlowFeed } from "./flowFeed";
import type { UnusualOptionsFlow } from "./types";

const tslaFlow: UnusualOptionsFlow = {
  ok: true,
  symbol: "TSLA",
  n_scanned: 10,
  flags: [
    {
      symbol: "TSLA",
      expiry: "2026-08-21",
      dte: 33,
      right: "C",
      strike: 350,
      volume: 600,
      premium: 300_000,
      score: 70,
      reasons: [],
      trade_time: "2026-07-16T18:30:00.000Z",
    },
    {
      symbol: "TSLA",
      expiry: "2026-08-21",
      dte: 33,
      right: "P",
      strike: 250,
      volume: 200,
      premium: 100_000,
      score: 50,
      reasons: [],
      trade_time: "2026-07-16T18:45:00.000Z",
    },
  ],
  asof_utc: "2026-07-16T18:45:00.000Z",
};

const nvdaFlow: UnusualOptionsFlow = {
  ok: true,
  symbol: "NVDA",
  n_scanned: 5,
  flags: [
    {
      symbol: "NVDA",
      expiry: "2026-08-07",
      dte: 19,
      right: "C",
      strike: 200,
      volume: 900,
      premium: 500_000,
      score: 80,
      reasons: [],
      trade_time: "2026-07-16T18:40:00.000Z",
    },
  ],
  asof_utc: "2026-07-16T18:40:00.000Z",
};

const feed = mergeFlowFeed(
  [
    { symbol: "TSLA", flow: tslaFlow },
    { symbol: "NVDA", flow: nvdaFlow },
    { symbol: "SPY", error: "scan timeout" },
  ],
  { now: new Date("2026-07-16T19:00:00Z") },
);

assert.equal(feed.ok, true);
assert.equal(feed.entries.length, 3);
// Newest print first
assert.equal(feed.entries[0].symbol, "TSLA");
assert.equal(feed.entries[0].right, "P");
assert.equal(feed.entries[1].symbol, "NVDA");
assert.equal(feed.entries[2].right, "C");
assert.equal(feed.n_scanned, 15);
assert.equal(feed.errors.SPY, "scan timeout");
assert.equal(feed.asof_utc, "2026-07-16T18:45:00.000Z");

assert.equal(feed.summary.call_premium, 800_000);
assert.equal(feed.summary.put_premium, 100_000);
assert.equal(feed.summary.call_count, 2);
assert.equal(feed.summary.put_count, 1);
assert.equal(feed.summary.sentiment, "bullish");
assert.equal(feed.summary.bullish_pct, 88.9);

// All sources failing → not ok
const dead = mergeFlowFeed([{ symbol: "SPY", error: "down" }]);
assert.equal(dead.ok, false);
assert.equal(dead.entries.length, 0);
assert.equal(dead.summary.sentiment, "neutral");

console.log("flow feed merge checks passed");
