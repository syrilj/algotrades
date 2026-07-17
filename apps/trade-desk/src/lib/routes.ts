/** Canonical client routes + hub tab contracts for Trade Desk. */

export type AnalyzeQuery = {
  symbol?: string;
  model?: string;
};

/** Command Analyze desk. Prefer this over legacy `/analyze` or bare `/`. */
export function analyzeHref(q: AnalyzeQuery = {}): string {
  const params = new URLSearchParams();
  const symbol = q.symbol?.trim().toUpperCase();
  const model = q.model?.trim();
  if (symbol) params.set("symbol", symbol);
  if (model) params.set("model", model);
  const qs = params.toString();
  return qs ? `/command?${qs}` : "/command";
}

// ---------------------------------------------------------------------------
// Ops hub (/live) — Discover (Radar) + Execute in one operator workspace
// ---------------------------------------------------------------------------

/**
 * Modes ordered Discover → Operate → Structure.
 * Radar (bias/picks/supply-chain) and Execution (watch/ticket/options/gamma)
 * share this hub so discovery and decision share symbol/account context.
 */
export type LiveMode =
  | "bias"
  | "flow"
  | "picks"
  | "supply-chain"
  | "watch"
  | "ticket"
  | "options"
  | "gamma";

const LIVE_MODES: readonly LiveMode[] = [
  "bias",
  "flow",
  "picks",
  "supply-chain",
  "watch",
  "ticket",
  "options",
  "gamma",
];

const LIVE_MODE_SET = new Set<string>(LIVE_MODES);

export function resolveLiveMode(raw: string | null | undefined): LiveMode {
  if (raw && LIVE_MODE_SET.has(raw)) return raw as LiveMode;
  // legacy aliases
  if (raw === "risk" || raw === "decision") return "ticket";
  if (raw === "scan" || raw === "radar") return "bias";
  if (raw === "chain" || raw === "supply") return "supply-chain";
  if (
    raw === "money-flow" ||
    raw === "money_flow" ||
    raw === "rotation" ||
    raw === "sectors"
  ) {
    return "flow";
  }
  // default: decision workspace (empty state teaches the path)
  return "ticket";
}

/** Ops hub — default tab is risk ticket / decision. */
export function liveHref(
  symbol?: string,
  mode: LiveMode = "ticket",
  account?: number,
): string {
  const s = symbol?.trim().toUpperCase();
  const params = new URLSearchParams();
  if (mode !== "ticket") params.set("mode", mode);
  if (s) params.set("symbol", s);
  if (account != null && Number.isFinite(account) && account > 0) {
    params.set("account", String(account));
  }
  const qs = params.toString();
  return qs ? `/live?${qs}` : "/live";
}

export function watchHref(symbol?: string, account?: number): string {
  return liveHref(symbol, "watch", account);
}

export function optionsHref(symbol?: string, account?: number): string {
  return liveHref(symbol, "options", account);
}

export function gammaHref(symbol?: string, account?: number): string {
  return liveHref(symbol, "gamma", account);
}

export function liveHubTabs(
  symbol?: string,
  account?: number,
): { key: LiveMode; label: string; href: string }[] {
  return [
    { key: "bias", label: "Bias", href: liveHref(symbol, "bias", account) },
    { key: "flow", label: "Flow", href: liveHref(symbol, "flow", account) },
    { key: "picks", label: "Picks", href: liveHref(symbol, "picks", account) },
    {
      key: "supply-chain",
      label: "Chain",
      href: liveHref(symbol, "supply-chain", account),
    },
    { key: "watch", label: "Watch", href: watchHref(symbol, account) },
    { key: "ticket", label: "Decision", href: liveHref(symbol, "ticket", account) },
    { key: "options", label: "Options", href: optionsHref(symbol, account) },
    { key: "gamma", label: "Gamma", href: gammaHref(symbol, account) },
  ];
}

export const LIVE_MODE_DESCRIPTIONS: Record<LiveMode, string> = {
  bias:
    "Market bias scan (VPA / VWAP DNA). Research checklist — not auto-execution.",
  flow:
    "Sector money flow — where capital is rotating in/out, how definitive it looks, and what to keep in mind.",
  picks:
    "Horizon + sector scan for live setups. Click a name to open a decision ticket.",
  "supply-chain":
    "Seed a mega-cap, map suppliers, and surface correlated small-cap plays.",
  watch:
    "Multi-symbol operator board. Market scan ranks plays; poll keeps levels fresh. Click a name for a ticket.",
  ticket:
    "Build a paper plan with a verified price, clear stop, safe size, and maximum loss.",
  options:
    "Compare a defined-risk options idea, its cost, time window, and payoff shape.",
  gamma:
    "Live gamma feed from option flow (OI fallback). Walls, squeeze, and listed expiries — not invented calendar dates.",
};

/** Deep link into the money-flow / rotation board. */
export function moneyFlowHref(symbol?: string, account?: number): string {
  return liveHref(symbol, "flow", account);
}

// ---------------------------------------------------------------------------
// Legacy Radar hub (/scan) — aliases into Ops modes
// ---------------------------------------------------------------------------

export type ScanView = "bias" | "picks" | "supply-chain";

export function resolveScanView(raw: string | null | undefined): ScanView {
  if (raw === "picks" || raw === "supply-chain") return raw;
  return "bias";
}

/** @deprecated Prefer liveHref(symbol, view). Kept for legacy call sites. */
export function scanHref(view: ScanView = "bias", symbol?: string): string {
  return liveHref(symbol, view);
}

/** @deprecated Prefer liveHubTabs. */
export function scanHubTabs(symbol?: string): {
  key: ScanView;
  label: string;
  href: string;
}[] {
  return [
    { key: "bias", label: "Market Bias", href: scanHref("bias", symbol) },
    { key: "picks", label: "Picks", href: scanHref("picks", symbol) },
    {
      key: "supply-chain",
      label: "Supply Chain",
      href: scanHref("supply-chain", symbol),
    },
  ];
}

// ---------------------------------------------------------------------------
// Portfolio hub (/positions)
// ---------------------------------------------------------------------------

export type PositionsView = "open" | "portfolio" | "history";

export function resolvePositionsView(
  raw: string | null | undefined,
): PositionsView {
  if (raw === "portfolio" || raw === "history") return raw;
  return "open";
}

export function positionsHref(view: PositionsView = "open"): string {
  if (view === "open") return "/positions";
  return `/positions?view=${view}`;
}

export function positionsHubTabs(): {
  key: PositionsView;
  label: string;
  href: string;
}[] {
  return [
    { key: "open", label: "Open Positions", href: positionsHref("open") },
    { key: "portfolio", label: "Portfolio", href: positionsHref("portfolio") },
    {
      key: "history",
      label: "History / Risk",
      href: positionsHref("history"),
    },
  ];
}

// ---------------------------------------------------------------------------
// Lab hub (/research)
// ---------------------------------------------------------------------------

export type ResearchView = "leaderboard" | "models" | "evolve" | "backtest";

export function resolveResearchView(
  raw: string | null | undefined,
): ResearchView {
  if (
    raw === "leaderboard" ||
    raw === "models" ||
    raw === "evolve" ||
    raw === "backtest"
  ) {
    return raw;
  }
  return "leaderboard";
}

export function researchHref(
  view: ResearchView = "leaderboard",
  symbol?: string,
): string {
  const s = symbol?.trim().toUpperCase();
  const params = new URLSearchParams();
  params.set("view", view);
  if (s) params.set("symbol", s);
  return `/research?${params.toString()}`;
}

export function researchHubTabs(symbol?: string): {
  key: ResearchView;
  label: string;
  href: string;
}[] {
  return [
    {
      key: "leaderboard",
      label: "Leaderboard",
      href: researchHref("leaderboard", symbol),
    },
    {
      key: "models",
      label: "Model Catalog",
      href: researchHref("models", symbol),
    },
    { key: "evolve", label: "Evolve Farm", href: researchHref("evolve") },
    { key: "backtest", label: "Backtest", href: researchHref("backtest") },
  ];
}

/** Prefer Lab hub over legacy `/leaderboard` standalone. */
export function leaderboardHref(symbol?: string): string {
  return researchHref("leaderboard", symbol);
}

export function modelHref(id: string): string {
  return `/models/${encodeURIComponent(id)}`;
}

export function supplyChainHref(symbol?: string): string {
  return liveHref(symbol, "supply-chain");
}

/** Shared panel id contract for HubTabs aria-controls. */
export function hubPanelId(key: string): string {
  return `hub-panel-${key}`;
}

// Keep for type exhaustiveness checks in tests/tooling.
export const HUB_KEYS = {
  live: LIVE_MODES,
} as const;
