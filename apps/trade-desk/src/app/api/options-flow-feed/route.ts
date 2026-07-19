import { NextResponse } from "next/server";

import { sanitizeSymbol } from "@/lib/format";
import { mergeFlowFeed, type FlowFeedSource, type OptionsFlowFeed } from "@/lib/flowFeed";
import { runOptionsUnusualFlow } from "@/lib/tradeDesk";
import type { ApiEnvelope, UnusualOptionsFlow } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 120;

const DEFAULT_WATCHLIST = [
  "SPY",
  "QQQ",
  "NVDA",
  "TSLA",
  "AAPL",
  "AMD",
  "META",
  "MSTR",
  "COIN",
  "PLTR",
  "IONQ",
] as const;

function envelope<T>(
  partial: Omit<ApiEnvelope<T>, "asof"> & { asof?: string },
  status: number,
): NextResponse {
  const body: ApiEnvelope<T> = {
    ...partial,
    asof: partial.asof ?? new Date().toISOString(),
  };
  return NextResponse.json(body, { status });
}

type Body = {
  symbols?: string;
  maxDte?: number | string;
  top?: number | string;
  limit?: number | string;
};

export async function POST(req: Request) {
  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    return envelope(
      { ok: false, command: "options-flow-feed", error: "Invalid JSON body" },
      400,
    );
  }

  const symbols = (body.symbols ?? DEFAULT_WATCHLIST.join(","))
    .split(",")
    .map((s) => sanitizeSymbol(s))
    .filter((s): s is string => Boolean(s));
  if (symbols.length === 0) {
    return envelope(
      { ok: false, command: "options-flow-feed", error: "symbols required" },
      400,
    );
  }

  const maxDte = body.maxDte != null ? Number(body.maxDte) : 45;
  const top = body.top != null ? Number(body.top) : 40;
  const limit = body.limit != null ? Number(body.limit) : 120;

  const args = (symbol: string) => {
    const a = ["--symbol", symbol];
    if (Number.isFinite(maxDte) && maxDte > 0) a.push("--max-dte", String(maxDte));
    if (Number.isFinite(top) && top > 0) a.push("--top", String(top));
    return a;
  };

  const sources: FlowFeedSource[] = await Promise.all(
    symbols.map(async (symbol): Promise<FlowFeedSource> => {
      try {
        const flow = (await runOptionsUnusualFlow(
          args(symbol),
          60_000,
        )) as UnusualOptionsFlow;
        return { symbol, flow };
      } catch (e) {
        return { symbol, error: e instanceof Error ? e.message : String(e) };
      }
    }),
  );

  const feed = mergeFlowFeed(sources, {
    limit: Number.isFinite(limit) && limit > 0 ? limit : 120,
  });
  if (!feed.ok) {
    const firstError = Object.values(feed.errors)[0] ?? "all symbol scans failed";
    return envelope<OptionsFlowFeed>(
      { ok: false, command: "options-flow-feed", error: firstError, data: feed },
      502,
    );
  }
  return envelope<OptionsFlowFeed>(
    { ok: true, command: "options-flow-feed", data: feed, asof: feed.asof_utc },
    200,
  );
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const body: Body = {
    symbols: url.searchParams.get("symbols") || undefined,
    maxDte: url.searchParams.get("maxDte") || undefined,
    top: url.searchParams.get("top") || undefined,
    limit: url.searchParams.get("limit") || undefined,
  };
  const fakeReq = new Request(req.url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return POST(fakeReq);
}
