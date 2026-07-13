/** Canonical client routes for Trade Desk deep-links. */

export type AnalyzeQuery = {
  symbol?: string;
  model?: string;
};

/** Home Analyze desk. Prefer this over legacy `/analyze`. */
export function analyzeHref(q: AnalyzeQuery = {}): string {
  const params = new URLSearchParams();
  const symbol = q.symbol?.trim().toUpperCase();
  const model = q.model?.trim();
  if (symbol) params.set("symbol", symbol);
  if (model) params.set("model", model);
  const qs = params.toString();
  return qs ? `/?${qs}` : "/";
}

export function liveHref(symbol?: string): string {
  const s = symbol?.trim().toUpperCase();
  if (!s) return "/live";
  return `/live?symbol=${encodeURIComponent(s)}`;
}

export function optionsHref(symbol?: string): string {
  const s = symbol?.trim().toUpperCase();
  if (!s) return "/live?mode=options";
  return `/live?mode=options&symbol=${encodeURIComponent(s)}`;
}

export function leaderboardHref(symbol?: string): string {
  const s = symbol?.trim().toUpperCase();
  if (!s) return "/leaderboard";
  return `/leaderboard?symbol=${encodeURIComponent(s)}`;
}

export function modelHref(id: string): string {
  return `/models/${encodeURIComponent(id)}`;
}

export function positionsHref(): string {
  return "/positions";
}

export function supplyChainHref(symbol?: string): string {
  const s = symbol?.trim().toUpperCase();
  if (!s) return "/supply-chain";
  return `/supply-chain?symbol=${encodeURIComponent(s)}`;
}
