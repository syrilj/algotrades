/**
 * Action / mode color resolution tests — run with:
 *   npx sucrase-node src/lib/actionColors.test.ts
 */
import assert from "node:assert/strict";
import { colorVarFor, matchActionVarName } from "./actionColors";

function check(name: string, fn: () => void) {
  try {
    fn();
    console.log(`ok  ${name}`);
  } catch (e) {
    console.error(`FAIL ${name}`);
    throw e;
  }
}

check("risk ticket modes resolve through action path (not bare EQUITY accent)", () => {
  // EQUITY_HEDGE must not pick up the bare EQUITY buy-breakout tone
  assert.equal(
    colorVarFor("mode", "EQUITY_HEDGE"),
    "var(--td-action-wait)",
  );
  assert.equal(
    colorVarFor("mode", "STAND_ASIDE"),
    "var(--td-action-avoid)",
  );
  assert.equal(
    colorVarFor("mode", "RISK_OK"),
    "var(--td-action-buy-now)",
  );
  assert.equal(
    colorVarFor("mode", "SIZE_DOWN"),
    "var(--td-action-breakout-watch)",
  );
  assert.equal(
    colorVarFor("mode", "FLATTEN"),
    "var(--td-action-avoid)",
  );
});

check("options vehicle modes keep OPTIONS / EQUITY accents", () => {
  assert.equal(colorVarFor("mode", "OPTIONS"), "var(--td-action-buy-now)");
  assert.equal(colorVarFor("mode", "EQUITY"), "var(--td-action-buy-breakout)");
});

check("gates and actions use shared path", () => {
  assert.equal(colorVarFor("gate", "pass"), "var(--td-gate-pass)");
  assert.equal(colorVarFor("gate", "fail"), "var(--td-gate-fail)");
  assert.equal(matchActionVarName("BUY NOW"), "--td-action-buy-now");
  assert.equal(matchActionVarName("AVOID"), "--td-action-avoid");
});

console.log("\nAll action color checks passed.");
