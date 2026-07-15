import { NextResponse } from "next/server";

import { sanitizeSymbol } from "@/lib/format";
import { runGammaExposure } from "@/lib/tradeDesk";
import type { ApiEnvelope, GammaResponse } from "@/lib/types";

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
  spotSource?: "auto" | "lse" | "yfinance";
  source?: "auto" | "oi" | "lse";
  expiryFrom?: string;
  expiryTo?: string;
  maxExpiries?: number | string;
  maxDte?: number | string;
};

export async function POST(req: Request) {
  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    return envelope({ ok: false, command: "gamma", error: "Invalid JSON body" }, 400);
  }

  const symbol = sanitizeSymbol(body.symbol);
  if (!symbol) {
    return envelope({ ok: false, command: "gamma", error: "symbol required" }, 400);
  }

  const args = ["--symbol", symbol];
  if (body.spotSource) {
    args.push("--spot-source", body.spotSource);
  }
  if (body.source) {
    args.push("--source", body.source);
  }
  if (body.expiryFrom && /^\d{4}-\d{2}-\d{2}$/.test(body.expiryFrom)) {
    args.push("--expiry-from", body.expiryFrom);
  }
  if (body.expiryTo && /^\d{4}-\d{2}-\d{2}$/.test(body.expiryTo)) {
    args.push("--expiry-to", body.expiryTo);
  }
  const maxExpiries = body.maxExpiries != null ? Number(body.maxExpiries) : undefined;
  if (maxExpiries != null && Number.isFinite(maxExpiries) && maxExpiries > 0) {
    args.push("--max-expiries", String(maxExpiries));
  }
  const maxDte = body.maxDte != null ? Number(body.maxDte) : undefined;
  if (maxDte != null && Number.isFinite(maxDte) && maxDte > 0) {
    args.push("--max-dte", String(maxDte));
  }

  try {
    const data = (await runGammaExposure(args, 90_000)) as GammaResponse;
    if (data && "error" in data && data.error) {
      return envelope(
        { ok: false, command: "gamma", error: data.error, data },
        422,
      );
    }
    return envelope(
      { ok: true, command: "gamma", data, asof: data.asof_utc },
      200,
    );
  } catch (e) {
    return envelope(
      {
        ok: false,
        command: "gamma",
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
    spotSource: (url.searchParams.get("spotSource") as Body["spotSource"]) || undefined,
    source: (url.searchParams.get("source") as Body["source"]) || undefined,
    expiryFrom: url.searchParams.get("expiryFrom") || undefined,
    expiryTo: url.searchParams.get("expiryTo") || undefined,
    maxExpiries: url.searchParams.get("maxExpiries") || undefined,
    maxDte: url.searchParams.get("maxDte") || undefined,
  };

  const fakeReq = new Request(req.url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return POST(fakeReq);
}
