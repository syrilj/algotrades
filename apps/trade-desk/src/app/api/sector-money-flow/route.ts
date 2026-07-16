import { NextResponse } from "next/server";

import { runSectorMoneyFlow } from "@/lib/tradeDesk";
import type { ApiEnvelope } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 120;

type Body = {
  source?: "auto" | "local" | "yfinance";
  period?: string;
  benchmark?: string;
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

function parseSource(raw: string | null | undefined): "auto" | "local" | "yfinance" {
  if (raw === "local" || raw === "yfinance" || raw === "auto") return raw;
  return "auto";
}

/**
 * Sector money-flow scanner — where capital is rotating (OHLCV RS proxy).
 * Research surface; not live auto-execution.
 */
export async function GET(req: Request) {
  const url = new URL(req.url);
  return runFlow({
    source: parseSource(url.searchParams.get("source")),
    period: url.searchParams.get("period") ?? "6mo",
    benchmark: url.searchParams.get("benchmark") ?? "SPY",
  });
}

export async function POST(req: Request) {
  let body: Body = {};
  try {
    body = (await req.json()) as Body;
  } catch {
    // defaults
  }
  return runFlow({
    source: parseSource(body.source),
    period: body.period ?? "6mo",
    benchmark: body.benchmark ?? "SPY",
  });
}

async function runFlow(opts: {
  source: "auto" | "local" | "yfinance";
  period: string;
  benchmark: string;
}): Promise<NextResponse> {
  try {
    const args = [
      "--source",
      opts.source,
      "--period",
      opts.period,
      "--benchmark",
      opts.benchmark,
    ];
    const data = await runSectorMoneyFlow(args, 90_000);
    const report = data as { ok?: boolean; error?: string; asof?: string };
    if (report?.ok === false) {
      return envelope(
        {
          ok: false,
          command: "sector-money-flow",
          error: report.error || "sector money flow failed",
          data: report,
        },
        502,
      );
    }
    return envelope(
      {
        ok: true,
        command: "sector-money-flow",
        data: report,
        asof: report.asof,
      },
      200,
    );
  } catch (e) {
    return envelope(
      {
        ok: false,
        command: "sector-money-flow",
        error: e instanceof Error ? e.message : String(e),
      },
      500,
    );
  }
}
