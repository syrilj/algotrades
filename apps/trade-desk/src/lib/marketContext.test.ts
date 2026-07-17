/**
 * Market context shaping tests — run with:
 *   npx sucrase-node src/lib/marketContext.test.ts
 */
import assert from "node:assert/strict";
import {
  buildMarketCalendarIcs,
  eventCountdown,
  marketEventsFromLse,
  summarizeSectorFlow,
  upcomingMarketEvents,
} from "./marketContext";

function check(name: string, fn: () => void) {
  try {
    fn();
    console.log(`ok  ${name}`);
  } catch (e) {
    console.error(`FAIL ${name}`);
    throw e;
  }
}

check("calendar returns the next verified high-impact event", () => {
  const events = upcomingMarketEvents(new Date("2026-07-16T18:00:00Z"), 3);
  assert.equal(events.length, 3);
  assert.equal(events[0].id, "fomc-2026-07");
  assert.equal(events[1].id, "gdp-pce-2026-07");
});

check("countdown uses compact operator labels", () => {
  assert.equal(
    eventCountdown("2026-07-17T14:00:00Z", new Date("2026-07-16T14:00:00Z")),
    "in 1d",
  );
  assert.equal(
    eventCountdown("2026-07-16T19:00:00Z", new Date("2026-07-16T14:00:00Z")),
    "in 5h",
  );
});

check("LSE calendar rows normalize and minor releases are excluded", () => {
  const events = marketEventsFromLse(
    [
      {
        datetime: "2026-07-29 18:00:00",
        region: "US",
        event: "FOMC interest rate decision",
        importance: "high",
        forecast: "4.25%",
      },
      {
        datetime: "2026-07-20 12:00:00",
        region: "US",
        event: "Weekly refinery utilization",
        importance: "low",
      },
    ],
    new Date("2026-07-16T18:00:00Z"),
  );
  assert.equal(events.length, 1);
  assert.equal(events[0].shortLabel, "FOMC");
  assert.equal(events[0].source, "London Strategic Edge");
  assert.match(events[0].note, /forecast 4.25%/);
});

check("sector report condenses to leader, laggard, and risk tone", () => {
  const context = summarizeSectorFlow({
    asof_bar: "2026-07-15",
    rotation: {
      is_definitive: true,
      confidence: 0.77,
      money_in_etfs: ["XLC", "XLE", "QQQ"],
      money_out_etfs: ["IGV", "XLV"],
    },
    sectors_ranked: [
      { etf: "XLC", name: "Comm", rs_1d: 0.0059, flow_direction: "in" },
      { etf: "XLE", name: "Energy", rs_1d: 0.0004, flow_direction: "in" },
      { etf: "IGV", name: "Software", rs_1d: -0.02, flow_direction: "out" },
    ],
  });
  assert.equal(context.tone, "risk-on");
  assert.equal(context.label, "XLC leads");
  assert.equal(context.laggard?.etf, "IGV");
  assert.equal(context.confidence, 0.77);
});

check("calendar export includes reminders and no expired events", () => {
  const ics = buildMarketCalendarIcs(new Date("2026-07-16T18:00:00Z"));
  assert.match(ics, /BEGIN:VCALENDAR/);
  assert.match(ics, /BEGIN:VALARM/);
  assert.match(ics, /Market: FOMC rate decision/);
  assert.doesNotMatch(ics, /2026-06/);
});

console.log("\nAll market context checks passed.");
