import { NextResponse } from "next/server";

import { sanitizeSymbol } from "@/lib/format";
import { runOptionsUnusualFlow } from "@/lib/tradeDesk";
import type { ApiEnvelope, UnusualOptionsFlow } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 120;

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
  symbol?: string;
  maxExpiries?: number | string;
  maxDte?: number | string;
  top?: number | string;
};

export async function POST(req: Request) {
  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    return envelope(
      { ok: false, command: "options-flow", error: "Invalid JSON body" },
      400,
    );
  }

  const symbol = sanitizeSymbol(body.symbol);
  if (!symbol) {
    return envelope(
      { ok: false, command: "options-flow", error: "symbol required" },
      400,
    );
  }

  const args = ["--symbol", symbol];
  const maxExpiries = body.maxExpiries != null ? Number(body.maxExpiries) : 6;
  if (Number.isFinite(maxExpiries) && maxExpiries > 0) {
    args.push("--max-expiries", String(maxExpiries));
  }
  const maxDte = body.maxDte != null ? Number(body.maxDte) : 45;
  if (Number.isFinite(maxDte) && maxDte > 0) {
    args.push("--max-dte", String(maxDte));
  }
  const top = body.top != null ? Number(body.top) : 20;
  if (Number.isFinite(top) && top > 0) {
    args.push("--top", String(top));
  }

  try {
    const data = (await runOptionsUnusualFlow(args, 90_000)) as UnusualOptionsFlow;
    if (data && data.ok === false && data.error) {
      return envelope(
        { ok: false, command: "options-flow", error: data.error, data },
        422,
      );
    }
    return envelope(
      {
        ok: true,
        command: "options-flow",
        data,
        asof: data.asof_utc ?? new Date().toISOString(),
      },
      200,
    );
  } catch (e) {
    return envelope(
      {
        ok: false,
        command: "options-flow",
        error: e instanceof Error ? e.message : String(e),
      },
      502,
    );
  }
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const body: Body = {
    symbol: url.searchParams.get("symbol") || undefined,
    maxExpiries: url.searchParams.get("maxExpiries") || undefined,
    maxDte: url.searchParams.get("maxDte") || undefined,
    top: url.searchParams.get("top") || undefined,
  };
  const fakeReq = new Request(req.url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return POST(fakeReq);
}
