import { NextResponse } from "next/server";

import { sanitizeSymbol } from "@/lib/format";
import { runLivePlan } from "@/lib/tradeDesk";
import type { ApiEnvelope, LivePlanResponse, LiveScanResponse } from "@/lib/types";

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
  account?: number | string;
  peak?: number | string;
  history?: string;
  openEquity?: number | string;
  openOptions?: number | string;
  model?: string;
  noModel?: boolean;
  scan?: boolean;
  symbols?: string;
  portfolioVerified?: boolean;
};

export async function POST(req: Request) {
  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    return envelope(
      { ok: false, command: "live-plan", error: "Invalid JSON body" },
      400,
    );
  }

  const account = body.account != null ? Number(body.account) : 1000;
  if (!Number.isFinite(account) || account <= 0) {
    return envelope(
      { ok: false, command: "live-plan", error: "Invalid account" },
      400,
    );
  }

  const args: string[] = ["--account", String(account)];

  if (body.peak != null && body.peak !== "") {
    const peak = Number(body.peak);
    if (Number.isFinite(peak) && peak > 0) {
      args.push("--peak", String(peak));
    }
  }
  if (typeof body.history === "string" && body.history.trim()) {
    args.push("--history", body.history.trim());
  }
  for (const [flag, value] of [
    ["--open-equity", body.openEquity],
    ["--open-options", body.openOptions],
  ] as const) {
    if (value == null || value === "") continue;
    const count = Number(value);
    if (Number.isInteger(count) && count >= 0) args.push(flag, String(count));
  }
  if (typeof body.model === "string" && body.model.trim()) {
    args.push("--model", body.model.trim());
  }
  if (body.noModel) {
    args.push("--no-model");
  }
  if (body.portfolioVerified) {
    args.push("--portfolio-verified");
  }

  if (body.scan) {
    args.push("--scan");
    if (typeof body.symbols === "string" && body.symbols.trim()) {
      args.push("--symbols", body.symbols.trim());
    }
    try {
      const data = (await runLivePlan(args, 120_000)) as LiveScanResponse;
      return envelope(
        {
          ok: true,
          command: "live-scan",
          data,
          asof: data.asof_utc,
        },
        200,
      );
    } catch (e) {
      return envelope(
        {
          ok: false,
          command: "live-scan",
          error: e instanceof Error ? e.message : String(e),
        },
        502,
      );
    }
  }

  const symbol = sanitizeSymbol(body.symbol);
  if (!symbol) {
    return envelope(
      { ok: false, command: "live-plan", error: "symbol required" },
      400,
    );
  }
  args.push("--symbol", symbol);

  try {
    const data = (await runLivePlan(args, 90_000)) as LivePlanResponse;
    if (data && data.ok === false) {
      return envelope(
        {
          ok: false,
          command: "live-plan",
          error: data.error || "live plan failed",
          data,
        },
        422,
      );
    }
    return envelope(
      {
        ok: true,
        command: "live-plan",
        data,
        asof: data.asof_utc,
      },
      200,
    );
  } catch (e) {
    return envelope(
      {
        ok: false,
        command: "live-plan",
        error: e instanceof Error ? e.message : String(e),
      },
      502,
    );
  }
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const symbol = sanitizeSymbol(url.searchParams.get("symbol"));
  const scan = url.searchParams.get("scan") === "1";
  const account = Number(url.searchParams.get("account") || "1000");
  const peak = url.searchParams.get("peak");
  const noModel = url.searchParams.get("noModel") === "1";

  const body: Body = {
    symbol: symbol ?? undefined,
    account,
    peak: peak ?? undefined,
    scan,
    noModel,
    symbols: url.searchParams.get("symbols") || undefined,
    history: url.searchParams.get("history") || undefined,
    model: url.searchParams.get("model") || undefined,
  };

  // Reuse POST logic
  const fakeReq = new Request(req.url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return POST(fakeReq);
}
