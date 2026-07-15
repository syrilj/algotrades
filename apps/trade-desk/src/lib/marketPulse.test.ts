/**
 * Market pulse shaping tests — run with:
 *   npx sucrase-node src/lib/marketPulse.test.ts
 */
import assert from "node:assert/strict";
import {
  buildMarketPulseSeries,
  fearGreedLabel,
  fearGreedTone,
  finiteOrNull,
  quoteTone,
  vixTone,
} from "./marketPulse";

function check(name: string, fn: () => void) {
  try {
    fn();
    console.log(`ok  ${name}`);
  } catch (e) {
    console.error(`FAIL ${name}`);
    throw e;
  }
}

check("buildMarketPulseSeries always emits VIX + F&G + WTI slots", () => {
  const empty = buildMarketPulseSeries({});
  assert.equal(empty.series.length, 3);
  assert.deepEqual(
    empty.series.map((s) => s.key),
    ["vix", "fear_greed", "oil"],
  );
  assert.equal(empty.ok, false);
  assert.ok(empty.series.every((s) => s.display === "—" || s.tone === "unavailable"));
});

check("live quotes shape display without inventing placeholders", () => {
  const payload = buildMarketPulseSeries({
    vix: { symbol: "^VIX", last: 16.2, prevClose: 15.8, source: "yfinance" },
    oil: { symbol: "CL=F", last: 78.45, prevClose: 79.1, source: "yfinance" },
    fearGreed: { value: 42, classification: "Fear", source: "alternative.me" },
    asof: "2026-07-15T12:00:00.000Z",
  });
  assert.equal(payload.ok, true);
  assert.equal(payload.series[0].display, "16.2");
  assert.equal(payload.series[0].value, 16.2);
  assert.equal(payload.series[1].display, "42 · Fear");
  assert.equal(payload.series[1].value, 42);
  assert.equal(payload.series[2].display, "$78.45");
  assert.equal(payload.series[2].value, 78.45);
  // Oil down day → down tone from quote delta
  assert.equal(payload.series[2].tone, "down");
});

check("partial failure leaves unavailable slots honest", () => {
  const payload = buildMarketPulseSeries({
    vix: { symbol: "^VIX", last: 22.5, prevClose: 21 },
    // oil missing, F&G missing
  });
  assert.equal(payload.ok, true);
  assert.equal(payload.series[0].display, "22.5");
  assert.equal(payload.series[1].tone, "unavailable");
  assert.equal(payload.series[2].tone, "unavailable");
  assert.equal(payload.series[2].display, "—");
});

check("vix / fear-greed tone helpers", () => {
  assert.equal(vixTone(12), "up");
  assert.equal(vixTone(30), "down");
  assert.equal(vixTone(null), "unavailable");
  assert.equal(fearGreedLabel(10), "Extreme Fear");
  assert.equal(fearGreedLabel(80), "Extreme Greed");
  assert.equal(fearGreedTone(30), "down");
  assert.equal(fearGreedTone(70), "up");
});

check("quoteTone and finiteOrNull", () => {
  assert.equal(quoteTone(10, 9).tone, "up");
  assert.equal(quoteTone(10, 11).tone, "down");
  assert.equal(finiteOrNull("42.5"), 42.5);
  assert.equal(finiteOrNull("nope"), null);
  assert.equal(finiteOrNull(undefined), null);
});

console.log("\nAll market pulse checks passed.");
