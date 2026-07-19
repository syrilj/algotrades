import type { UnusualOptionsFlag, UnusualOptionsFlow } from "./types";

/** One row of the multi-symbol active flow tape (newest print first). */
export type FlowFeedEntry = UnusualOptionsFlag;

export interface FlowFeedSummary {
  call_premium: number;
  put_premium: number;
  call_count: number;
  put_count: number;
  total_premium: number;
  /** Share of total premium in calls, 0–100. */
  bullish_pct: number;
  sentiment: "bullish" | "bearish" | "neutral";
}

export interface OptionsFlowFeed {
  ok: boolean;
  symbols: string[];
  entries: FlowFeedEntry[];
  summary: FlowFeedSummary;
  /** Per-symbol scan failures; feed stays partial-OK. */
  errors: Record<string, string>;
  n_scanned: number;
  asof_utc: string;
}

export interface FlowFeedSource {
  symbol: string;
  flow?: UnusualOptionsFlow | null;
  error?: string | null;
}

function isCall(right: string | undefined): boolean {
  const u = (right ?? "").toUpperCase();
  return u === "C" || u === "CALL";
}

function timeOf(entry: FlowFeedEntry): number {
  if (!entry.trade_time) return Number.NEGATIVE_INFINITY;
  const t = new Date(entry.trade_time).getTime();
  return Number.isFinite(t) ? t : Number.NEGATIVE_INFINITY;
}

export function summarizeFlow(entries: FlowFeedEntry[]): FlowFeedSummary {
  let callPremium = 0;
  let putPremium = 0;
  let callCount = 0;
  let putCount = 0;
  for (const e of entries) {
    const premium = e.premium ?? 0;
    if (isCall(e.right)) {
      callPremium += premium;
      callCount += 1;
    } else {
      putPremium += premium;
      putCount += 1;
    }
  }
  const total = callPremium + putPremium;
  const bullishPct = total > 0 ? (callPremium / total) * 100 : 50;
  return {
    call_premium: callPremium,
    put_premium: putPremium,
    call_count: callCount,
    put_count: putCount,
    total_premium: total,
    bullish_pct: Math.round(bullishPct * 10) / 10,
    sentiment: bullishPct >= 58 ? "bullish" : bullishPct <= 42 ? "bearish" : "neutral",
  };
}

/** Merge per-symbol unusual-flow scans into one time-ordered tape. */
export function mergeFlowFeed(
  sources: FlowFeedSource[],
  options: { limit?: number; now?: Date } = {},
): OptionsFlowFeed {
  const limit = Math.max(1, options.limit ?? 120);
  const now = options.now ?? new Date();
  const entries: FlowFeedEntry[] = [];
  const errors: Record<string, string> = {};
  const symbols: string[] = [];
  let nScanned = 0;
  let latest: string | null = null;

  for (const src of sources) {
    const symbol = src.symbol.toUpperCase();
    symbols.push(symbol);
    if (src.error || !src.flow) {
      errors[symbol] = src.error ?? "no flow data";
      continue;
    }
    if (src.flow.ok === false && src.flow.error) {
      errors[symbol] = src.flow.error;
      continue;
    }
    nScanned += src.flow.n_scanned ?? 0;
    if (src.flow.asof_utc && (!latest || src.flow.asof_utc > latest)) {
      latest = src.flow.asof_utc;
    }
    for (const flag of src.flow.flags ?? src.flow.unusual ?? []) {
      entries.push({ ...flag, symbol: flag.symbol || symbol });
    }
  }

  entries.sort((a, b) => {
    const dt = timeOf(b) - timeOf(a);
    if (dt !== 0) return dt;
    return b.score - a.score || (b.premium ?? 0) - (a.premium ?? 0);
  });

  const top = entries.slice(0, limit);
  return {
    ok: Object.keys(errors).length < sources.length,
    symbols,
    entries: top,
    summary: summarizeFlow(top),
    errors,
    n_scanned: nScanned,
    asof_utc: latest ?? now.toISOString(),
  };
}
