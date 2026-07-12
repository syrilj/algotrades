import { NextResponse } from "next/server";

import { runPortfolioOptimizer } from "@/lib/tradeDesk";
import type { ApiEnvelope } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

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
  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return envelope({ ok: false, command: "portfolio", error: "Invalid JSON" }, 400);
  }

  const method = String(body.method || "mpt");
  if (!["mpt", "risk_parity", "factor_tilt", "portfolio"].includes(method)) {
    return envelope(
      { ok: false, command: "portfolio", error: "method must be mpt | risk_parity | factor_tilt | portfolio" },
      400,
    );
  }

  try {
    const data = await runPortfolioOptimizer(body, 30_000);
    return envelope({ ok: true, command: "portfolio", data }, 200);
  } catch (e) {
    return envelope(
      {
        ok: false,
        command: "portfolio",
        error: e instanceof Error ? e.message : String(e),
      },
      502,
    );
  }
}
