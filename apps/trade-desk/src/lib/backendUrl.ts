/**
 * Production backend URL selection for Trade Desk.
 *
 * When MARKET_RUNTIME_URL is set (Vercel → Render/Cloud Run), core plan/analyze
 * calls go over HTTP. When unset, local dev may spawn Python (see tradeDesk.ts).
 */

export type EnvLike = Record<string, string | undefined> | NodeJS.ProcessEnv;

/** Normalize base URL: trim, strip trailing slash. Null if missing/blank. */
export function marketRuntimeBaseUrl(env: EnvLike = process.env): string | null {
  const raw = env.MARKET_RUNTIME_URL;
  if (typeof raw !== "string") return null;
  const url = raw.trim().replace(/\/+$/, "");
  if (!url) return null;
  return url;
}

export function planEndpointUrl(env: EnvLike = process.env): string | null {
  const base = marketRuntimeBaseUrl(env);
  return base ? `${base}/plan` : null;
}

export function analyzeEndpointUrl(env: EnvLike = process.env): string | null {
  const base = marketRuntimeBaseUrl(env);
  return base ? `${base}/analyze` : null;
}

/** Build a URL for a known market-runtime path. Callers own query validation. */
export function marketRuntimeEndpointUrl(
  endpoint: string,
  env: EnvLike = process.env,
): string | null {
  const base = marketRuntimeBaseUrl(env);
  if (!base) return null;
  const path = endpoint.trim().replace(/^\/+/, "");
  return path ? `${base}/${path}` : base;
}

/** True when production-style remote backend is configured. */
export function prefersRemoteBackend(env: EnvLike = process.env): boolean {
  return marketRuntimeBaseUrl(env) != null;
}
