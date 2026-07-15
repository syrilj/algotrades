import { NextResponse } from "next/server";

import { sanitizeSymbol } from "@/lib/format";
import { runAnalysisAgent } from "@/lib/tradeDesk";
import type { AnalysisAgentResponse, ApiEnvelope } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 120;

type Body = {
  symbol?: string;
  account?: number | string;
  model?: string;
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

export async function POST(req: Request) {
  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    return envelope(
      { ok: false, command: "analysis-agent", error: "Invalid JSON body" },
      400,
    );
  }

  const symbol = sanitizeSymbol(body.symbol);
  if (!symbol) {
    return envelope(
      { ok: false, command: "analysis-agent", error: "symbol required" },
      400,
    );
  }

  const account = body.account != null ? Number(body.account) : 1000;
  if (!Number.isFinite(account) || account <= 0) {
    return envelope(
      { ok: false, command: "analysis-agent", error: "Invalid account" },
      400,
    );
  }

  const args: string[] = ["--symbol", symbol, "--account", String(account)];

  if (typeof body.model === "string" && body.model.trim() && body.model !== "auto") {
    args.push("--model", body.model.trim());
  }

  try {
    const data = (await runAnalysisAgent(args, 120_000)) as AnalysisAgentResponse;
    if (data && data.ok === false) {
      return envelope(
        {
          ok: false,
          command: "analysis-agent",
          error: data.error || "analysis failed",
          data,
        },
        422,
      );
    }
    return envelope(
      {
        ok: true,
        command: "analysis-agent",
        data,
        asof: data.asof_utc,
      },
      200,
    );
  } catch (e) {
    return envelope(
      {
        ok: false,
        command: "analysis-agent",
        error: e instanceof Error ? e.message : String(e),
      },
      502,
    );
  }
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const symbol = sanitizeSymbol(url.searchParams.get("symbol"));
  const account = Number(url.searchParams.get("account") || "1000");
  const model = url.searchParams.get("model") || undefined;

  const body: Body = {
    symbol: symbol ?? undefined,
    account,
    model: model ?? undefined,
  };

  const fakeReq = new Request(req.url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return POST(fakeReq);
}
