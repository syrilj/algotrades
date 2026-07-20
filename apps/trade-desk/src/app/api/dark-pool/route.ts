import { NextResponse } from "next/server";

import type { ApiEnvelope, DarkPoolResponse } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 30;

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
  minNotional?: number | string;
  limit?: number | string;
};

export async function POST(req: Request) {
  let body: Body = {};
  try {
    body = (await req.json()) as Body;
  } catch {
    // empty body is fine
  }

  const minNotional = body.minNotional != null ? Number(body.minNotional) : 1_000_000;

  // Placeholder: a real dark-pool feed needs a TRF/ADF or Polygon stocks-trades WebSocket.
  const data: DarkPoolResponse = {
    ok: true,
    prints: [],
    asof_utc: new Date().toISOString(),
    note: `No dark-pool source configured. Wire a FINRA TRF/ADF or stocks-trades vendor feed to populate prints above ${new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(minNotional)} notional.`,
  };

  return envelope<DarkPoolResponse>(
    { ok: true, command: "dark-pool", data, asof: data.asof_utc },
    200,
  );
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const body: Body = {
    symbol: url.searchParams.get("symbol") || undefined,
    minNotional: url.searchParams.get("minNotional") || undefined,
    limit: url.searchParams.get("limit") || undefined,
  };
  const fakeReq = new Request(req.url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return POST(fakeReq);
}
