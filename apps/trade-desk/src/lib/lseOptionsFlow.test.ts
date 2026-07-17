import assert from "node:assert/strict";

import { normalizeLseOptionsFlow } from "./lseOptionsFlow";

const flow = normalizeLseOptionsFlow(
  [
    {
      ts: "2026-07-16 18:30:00",
      ticker: "TSLA260821C00350000",
      underlying: "TSLA",
      price: 5,
      size: 600,
      premium: 300000,
      underlying_price: 320,
      iv: 0.72,
    },
    {
      ts: "2026-07-16 18:31:00",
      ticker: "TSLA260821P00250000",
      price: 1,
      size: 10,
      premium: 1000,
    },
  ],
  "TSLA",
  { now: new Date("2026-07-16T18:00:00Z") },
);

assert.equal(flow.ok, true);
assert.equal(flow.n_scanned, 2);
assert.equal(flow.n_flagged, 1);
assert.equal(flow.flags[0].right, "C");
assert.equal(flow.flags[0].strike, 350);
assert.equal(flow.flags[0].premium, 300000);
assert.equal(flow.flags[0].methodology, "lse_options_time_and_sales");
assert.match(flow.flags[0].reason ?? "", /600 contracts/);
assert.equal(flow.asof_utc, "2026-07-16T18:30:00.000Z");

console.log("LSE options flow normalization checks passed");
