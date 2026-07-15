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

export type LiveMode = "ticket" | "watch" | "options" | "gamma";

/** Execution hub — default tab is risk ticket. */
export function liveHref(symbol?: string, mode: LiveMode = "ticket"): string {
  const s = symbol?.trim().toUpperCase();
  const params = new URLSearchParams();
  if (mode !== "ticket") params.set("mode", mode);
  if (s) params.set("symbol", s);
  const qs = params.toString();
  return qs ? `/live?${qs}` : "/live";
}

export function watchHref(): string {
  return "/live?mode=watch";
}

export function optionsHref(symbol?: string): string {
  return liveHref(symbol, "options");
}

export function gammaHref(symbol?: string): string {
  return liveHref(symbol, "gamma");
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
