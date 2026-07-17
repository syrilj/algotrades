import assert from "node:assert/strict";
import { POST } from "./route";


async function call(token?: string) {
  const headers = new Headers({ "content-type": "application/json" });
  if (token) headers.set("authorization", `Bearer ${token}`);
  return POST(
    new Request("http://localhost/api/promotion", {
      method: "POST",
      headers,
      body: JSON.stringify({ action: "invalid", id: "candidate" }),
    }),
  );
}

async function main() {
  delete process.env.PROMOTION_ADMIN_TOKEN;
  assert.equal((await call()).status, 503, "missing server token must fail closed");

  process.env.PROMOTION_ADMIN_TOKEN = "correct-secret";
  assert.equal((await call()).status, 401, "missing request token must be rejected");
  assert.equal((await call("wrong-secret")).status, 401, "mismatched token must be rejected");
  assert.equal((await call("correct-secret")).status, 400, "matching token must reach validation");
}

main()
  .then(() => console.log("promotion route authentication tests passed"))
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
