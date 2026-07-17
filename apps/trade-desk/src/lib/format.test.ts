/**
 * Format helper contract tests — run with:
 *   npx sucrase-node src/lib/format.test.ts
 */
import assert from "node:assert/strict";
import {
  formatNum,
  formatPct,
  formatPctPoints,
  formatPctPointsUnsigned,
  formatUsd,
  sanitizeSymbol,
} from "./format";

function check(name: string, fn: () => void) {
  try {
    fn();
    console.log(`ok  ${name}`);
  } catch (e) {
    console.error(`FAIL ${name}`);
    throw e;
  }
}

check("formatPct multiplies fractions once (not double-scaled)", () => {
  assert.equal(formatPct(0.135, 1), "+13.5%");
  assert.equal(formatPct(-0.134, 1), "-13.4%");
  assert.equal(formatPct(0, 1), "0.0%");
  assert.equal(formatPct(1, 0), "+100%");
  // Null / NaN stay honest dashes
  assert.equal(formatPct(null), "—");
  assert.equal(formatPct(Number.NaN), "—");
});

check("formatPctPoints does not re-scale percent points", () => {
  assert.equal(formatPctPoints(2.5, 1), "+2.5%");
  assert.equal(formatPctPoints(-1.2, 1), "-1.2%");
  assert.equal(formatPctPointsUnsigned(-3.4, 1), "3.4%");
  // If someone passes a fraction by mistake, points helper does NOT *100
  assert.equal(formatPctPoints(0.135, 1), "+0.1%");
});

check("formatUsd and formatNum handle null safely", () => {
  assert.equal(formatUsd(null), "—");
  assert.equal(formatUsd(101.5), "$101.50");
  assert.equal(formatNum(9), "9");
  assert.equal(formatNum(null), "—");
});

check("sanitizeSymbol strips junk and uppercases", () => {
  assert.equal(sanitizeSymbol("  tsla  "), "TSLA");
  assert.equal(sanitizeSymbol("MU.US"), "MU");
  assert.equal(sanitizeSymbol("INFQ"), "IONQ");
  assert.equal(sanitizeSymbol("googl"), "GOOG");
  assert.equal(sanitizeSymbol(""), null);
  assert.equal(sanitizeSymbol(12), null);
});

console.log("\nAll format helper checks passed.");
