import { NextResponse } from "next/server";

import { sanitizeSymbol } from "@/lib/format";
import { runSymbolRanker } from "@/lib/tradeDesk";
import type { ApiEnvelope, RankerResponse } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 300;

type RankPostBody = {
  symbol?: string;
  quick?: boolean;
  refresh?: boolean;
  maxSeconds?: number;
};

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

function asRankerResponse(raw: unknown): RankerResponse {
  return raw as RankerResponse;
}

async function showRanker(symbol: string): Promise<RankerResponse> {
  const raw = await runSymbolRanker(["show", symbol], 20_000);
  return asRankerResponse(raw);
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const symbol = sanitizeSymbol(url.searchParams.get("symbol"));
  if (!symbol) {
    return envelope(
      { ok: false, command: "symbol-rank", error: "symbol required" },
      400,
    );
  }

  try {
    const data = await showRanker(symbol);
    const asof =
      (typeof data.asof === "string" && data.asof) || new Date().toISOString();
    return envelope<RankerResponse>(
      { ok: true, command: "symbol-rank", data, asof },
      200,
    );
  } catch (e) {
    return envelope(
      {
        ok: false,
        command: "symbol-rank",
        error: e instanceof Error ? e.message : String(e),
      },
      502,
    );
  }
}

export async function POST(req: Request) {
  let body: RankPostBody = {};
  try {
    body = (await req.json()) as RankPostBody;
  } catch {
    return envelope(
      { ok: false, command: "symbol-rank", error: "Invalid JSON body" },
      400,
    );
  }

  const symbol = sanitizeSymbol(body.symbol);
  if (!symbol) {
    return envelope(
      { ok: false, command: "symbol-rank", error: "symbol required" },
      400,
    );
  }

  const maxSeconds = Math.min(
    280,
    Math.max(60, Number(body.maxSeconds ?? 240) || 240),
  );
  const args = [
    "rank",
    symbol,
    "--max-seconds",
    String(maxSeconds),
    ...(body.quick ? ["--quick"] : []),
    ...(body.refresh ? ["--refresh"] : []),
  ];

  try {
    const raw = await runSymbolRanker(args, 290_000);
    const data = asRankerResponse(raw);
    const asof =
      (typeof data.asof === "string" && data.asof) || new Date().toISOString();
    return envelope<RankerResponse>(
      { ok: true, command: "symbol-rank", data, asof },
      200,
    );
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    const timedOut = msg.includes("timed out");
    if (timedOut) {
      try {
        const data = await showRanker(symbol);
        if (data.status !== "complete") {
          data.status = "partial";
        }
        const asof =
          (typeof data.asof === "string" && data.asof) ||
          new Date().toISOString();
        return envelope<RankerResponse>(
          { ok: true, command: "symbol-rank", data, asof },
          200,
        );
      } catch {
        /* fall through */
      }
    }
    return envelope(
      { ok: false, command: "symbol-rank", error: msg },
      502,
    );
  }
}
