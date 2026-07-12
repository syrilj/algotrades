import { NextResponse } from "next/server";

import { sanitizeSymbol } from "@/lib/format";
import { runVpaScan } from "@/lib/tradeDesk";
import type { ApiEnvelope } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 180;

const DEFAULT_SYMBOLS =
  "TSLA,MSTR,NVDA,AMD,META,HOOD,IONQ,MU,AVGO,AAPL,AMZN,GOOGL,ARM";
const MAX_SYMBOLS = 24;

type ScanBody = {
  symbols?: string[] | string;
  withSectors?: boolean;
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

function parseSymbols(v: string[] | string | undefined): string[] {
  if (v == null) return [];
  if (Array.isArray(v)) return v.map(String);
  return String(v)
    .split(/[,\s]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/**
 * Research-only VPA + VWAP scan.
 * Never promoted to Live auto until 80% WR gate.
 */
export async function GET(req: Request) {
  const url = new URL(req.url);
  const raw =
    url.searchParams.get("symbols") ??
    url.searchParams.get("symbol") ??
    DEFAULT_SYMBOLS;
  const withSectors =
    url.searchParams.get("withSectors") === "1" ||
    url.searchParams.get("with_sectors") === "1" ||
    url.searchParams.get("sectors") === "1";
  return runScan(raw, withSectors);
}

export async function POST(req: Request) {
  let body: ScanBody = {};
  try {
    body = (await req.json()) as ScanBody;
  } catch {
    // empty body → defaults
  }
  const raw = body.symbols ?? DEFAULT_SYMBOLS;
  const withSectors = Boolean(body.withSectors);
  return runScan(raw, withSectors);
}

async function runScan(
  raw: string[] | string,
  withSectors: boolean,
): Promise<NextResponse> {
  const list = parseSymbols(raw);
  if (!list.length) {
    return envelope(
      { ok: false, command: "vpa-scan", error: "symbols required" },
      400,
    );
  }
  if (list.length > MAX_SYMBOLS) {
    return envelope(
      {
        ok: false,
        command: "vpa-scan",
        error: `Max ${MAX_SYMBOLS} symbols per scan`,
      },
      400,
    );
  }

  const symbols: string[] = [];
  for (const s of list) {
    const sym = sanitizeSymbol(s);
    if (!sym) {
      return envelope(
        { ok: false, command: "vpa-scan", error: `Invalid symbol: ${s}` },
        400,
      );
    }
    symbols.push(sym);
  }

  const args = ["--symbols", symbols.join(",")];
  if (withSectors) args.push("--with-sectors");

  try {
    const data = await runVpaScan(args, 180_000);
    return envelope(
      {
        ok: true,
        command: "vpa-scan",
        data,
      },
      200,
    );
  } catch (e) {
    return envelope(
      {
        ok: false,
        command: "vpa-scan",
        error: e instanceof Error ? e.message : String(e),
      },
      502,
    );
  }
}
