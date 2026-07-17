import assert from "node:assert/strict";
import {
  analyzeEndpointUrl,
  marketRuntimeBaseUrl,
  marketRuntimeEndpointUrl,
  planEndpointUrl,
  prefersRemoteBackend,
} from "./backendUrl";

function check(name: string, fn: () => void) {
  try {
    fn();
    console.log(`ok - ${name}`);
  } catch (e) {
    console.error(`FAIL - ${name}`);
    throw e;
  }
}

check("marketRuntimeBaseUrl null when unset", () => {
  assert.equal(marketRuntimeBaseUrl({}), null);
  assert.equal(marketRuntimeBaseUrl({ MARKET_RUNTIME_URL: "" }), null);
  assert.equal(marketRuntimeBaseUrl({ MARKET_RUNTIME_URL: "   " }), null);
});

check("marketRuntimeBaseUrl strips trailing slash", () => {
  assert.equal(
    marketRuntimeBaseUrl({ MARKET_RUNTIME_URL: "http://127.0.0.1:8000/" }),
    "http://127.0.0.1:8000",
  );
  assert.equal(
    marketRuntimeBaseUrl({ MARKET_RUNTIME_URL: "https://api.example.com/v1///" }),
    "https://api.example.com/v1",
  );
});

check("plan and analyze endpoints derive from base", () => {
  const env = { MARKET_RUNTIME_URL: "https://backend.example.com" };
  assert.equal(planEndpointUrl(env), "https://backend.example.com/plan");
  assert.equal(analyzeEndpointUrl(env), "https://backend.example.com/analyze");
  assert.equal(
    marketRuntimeEndpointUrl("/data/reference/economic_calendar", env),
    "https://backend.example.com/data/reference/economic_calendar",
  );
  assert.equal(prefersRemoteBackend(env), true);
  assert.equal(prefersRemoteBackend({}), false);
});

console.log("backendUrl tests passed");
