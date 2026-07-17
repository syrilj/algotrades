import { NextResponse } from "next/server";

import { sanitizeSymbol } from "@/lib/format";
import { runOptionsBookScan } from "@/lib/tradeDesk";
import type { ApiEnvelope, OptionsBookScanResponse } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 180;

const DEFAULT_BOOK = ["MSTR", "TSLA", "SKHY", "IONQ"];

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
  symbols?: string | string[];
  account?: number | string;
  risk_pct?: number | string;
  workers?: number | string;
};

function parseSymbols(raw: Body["symbols"]): string[] {
  const list: string[] = [];
  if (Array.isArray(raw)) {
    for (const item of raw) list.push(String(item));
  } else if (typeof raw === "string") {
    for (const part of raw.split(/[,\s]+/)) {
      if (part.trim()) list.push(part.trim());
    }
  }
  const out: string[] = [];
  const seen = new Set<string>();
  for (const item of list.length ? list : DEFAULT_BOOK) {
    const s = sanitizeSymbol(item);
    if (!s || seen.has(s)) continue;
    seen.add(s);
    out.push(s);
  }
  return out.length ? out : [...DEFAULT_BOOK];
}

export async function POST(req: Request) {
  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    return envelope(
      { ok: false, command: "options-book", error: "Invalid JSON body" },
      400,
    );
  }

  const symbols = parseSymbols(body.symbols);
  const account = body.account != null ? Number(body.account) : 1000;
  if (!Number.isFinite(account) || account <= 0) {
    return envelope(
      { ok: false, command: "options-book", error: "Invalid account" },
      400,
    );
  }

  const riskPct =
    body.risk_pct != null && body.risk_pct !== ""
      ? Number(body.risk_pct)
      : 18;
  const riskOk = Number.isFinite(riskPct) && riskPct > 0 && riskPct <= 100;
  const workers = body.workers != null ? Number(body.workers) : 4;

  const args = [
    "--symbols",
    symbols.join(","),
    "--account",
    String(account),
    "--json",
  ];
  if (riskOk) {
    // Python --risk-pct is a fraction; UI speaks percent points.
    args.push("--risk-pct", String(riskPct / 100));
  }
  if (Number.isFinite(workers) && workers > 0) {
    args.push("--workers", String(Math.min(8, Math.floor(workers))));
  }

  try {
    const data = (await runOptionsBookScan(
      args,
      180_000,
    )) as OptionsBookScanResponse;
    if (data && data.ok === false) {
      return envelope(
        {
          ok: false,
          command: "options-book",
          error: "options book scan failed",
          data,
        },
        422,
      );
    }
    return envelope(
      {
        ok: true,
        command: "options-book",
        data,
        asof: data.asof_utc ?? new Date().toISOString(),
      },
      200,
    );
  } catch (e) {
    return envelope(
      {
        ok: false,
        command: "options-book",
        error: e instanceof Error ? e.message : String(e),
      },
      502,
    );
  }
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const body: Body = {
    symbols: url.searchParams.get("symbols") || undefined,
    account: url.searchParams.get("account") || undefined,
    risk_pct: url.searchParams.get("risk_pct") || undefined,
    workers: url.searchParams.get("workers") || undefined,
  };
  const fakeReq = new Request(req.url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return POST(fakeReq);
}
