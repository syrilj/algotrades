/**
 * Route contract smoke tests — run with:
 *   npx sucrase-node src/lib/routes.test.ts
 */
import assert from "node:assert/strict";
import {
  analyzeHref,
  gammaHref,
  hubPanelId,
  leaderboardHref,
  liveHref,
  liveHubTabs,
  optionsHref,
  positionsHref,
  positionsHubTabs,
  researchHref,
  researchHubTabs,
  resolveLiveMode,
  resolvePositionsView,
  resolveResearchView,
  resolveScanView,
  scanHref,
  scanHubTabs,
  supplyChainHref,
  watchHref,
} from "./routes";

function check(name: string, fn: () => void) {
  try {
    fn();
    console.log(`ok  ${name}`);
  } catch (e) {
    console.error(`FAIL ${name}`);
    throw e;
  }
}

check("analyzeHref builds query", () => {
  assert.equal(analyzeHref(), "/");
  assert.equal(analyzeHref({ symbol: "tsla" }), "/?symbol=TSLA");
  assert.equal(
    analyzeHref({ symbol: "MU.US", model: "v39d_confluence" }),
    "/?symbol=MU.US&model=v39d_confluence",
  );
});

check("live modes resolve + preserve deep links", () => {
  assert.equal(resolveLiveMode(null), "ticket");
  assert.equal(resolveLiveMode("risk"), "ticket");
  assert.equal(resolveLiveMode("watch"), "watch");
  assert.equal(resolveLiveMode("bias"), "bias");
  assert.equal(resolveLiveMode("picks"), "picks");
  assert.equal(resolveLiveMode("supply-chain"), "supply-chain");
  assert.equal(resolveLiveMode("radar"), "bias");
  assert.equal(liveHref(), "/live");
  assert.equal(liveHref("aapl", "watch", 1000), "/live?mode=watch&symbol=AAPL&account=1000");
  assert.equal(watchHref("spy"), "/live?mode=watch&symbol=SPY");
  assert.equal(optionsHref("qqq", 5000), "/live?mode=options&symbol=QQQ&account=5000");
  assert.equal(gammaHref("tsla"), "/live?mode=gamma&symbol=TSLA");
  assert.equal(liveHref("nvda", "bias"), "/live?mode=bias&symbol=NVDA");
  assert.equal(liveHref(undefined, "picks"), "/live?mode=picks");
  assert.equal(resolveLiveMode("flow"), "flow");
  assert.equal(resolveLiveMode("money-flow"), "flow");
  assert.equal(resolveLiveMode("rotation"), "flow");
  assert.equal(liveHref(undefined, "flow"), "/live?mode=flow");
  assert.equal(liveHubTabs("TSLA", 1000).length, 8);
  assert.equal(
    liveHubTabs().map((t) => t.key).join(","),
    "bias,flow,picks,supply-chain,watch,ticket,options,gamma",
  );
});

check("scan hub aliases into live modes", () => {
  assert.equal(resolveScanView(null), "bias");
  assert.equal(resolveScanView("picks"), "picks");
  assert.equal(scanHref(), "/live?mode=bias");
  assert.equal(scanHref("picks"), "/live?mode=picks");
  assert.equal(
    scanHref("supply-chain", "nvda"),
    "/live?mode=supply-chain&symbol=NVDA",
  );
  assert.equal(supplyChainHref("AMD"), "/live?mode=supply-chain&symbol=AMD");
  assert.equal(scanHubTabs().length, 3);
});

check("positions hub routes", () => {
  assert.equal(resolvePositionsView(null), "open");
  assert.equal(resolvePositionsView("history"), "history");
  assert.equal(positionsHref(), "/positions");
  assert.equal(positionsHref("portfolio"), "/positions?view=portfolio");
  assert.equal(positionsHubTabs().map((t) => t.key).join(","), "open,portfolio,history");
});

check("research / lab hub routes", () => {
  assert.equal(resolveResearchView(null), "leaderboard");
  assert.equal(resolveResearchView("evolve"), "evolve");
  assert.equal(researchHref("models"), "/research?view=models");
  assert.equal(
    leaderboardHref("TSLA"),
    "/research?view=leaderboard&symbol=TSLA",
  );
  assert.equal(researchHubTabs().length, 4);
  assert.equal(hubPanelId("ticket"), "hub-panel-ticket");
});

console.log("\nAll route contract checks passed.");
