import { NextResponse } from "next/server";

import { sanitizeSymbol } from "@/lib/format";
import { runTradeDesk } from "@/lib/tradeDesk";
import type { ApiEnvelope, ModelRankRow } from "@/lib/types";

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

export async function GET(req: Request) {
  const url = new URL(req.url);
  const symbolRaw = url.searchParams.get("symbol");
  const enginesOnly =
    url.searchParams.get("enginesOnly") === "1" ||
    url.searchParams.get("engines-only") === "1";

  const args: string[] = ["rank"];

  if (symbolRaw) {
    const symbol = sanitizeSymbol(symbolRaw);
    if (!symbol) {
      return envelope(
        {
          ok: false,
          command: "rank",
          error: "Invalid symbol (alphanumeric)",
        },
        400,
      );
    }
    args.push("--symbol", symbol);
  }

  if (enginesOnly) {
    args.push("--engines-only");
  }

  try {
    const data = (await runTradeDesk(args)) as ModelRankRow[];
    return envelope<ModelRankRow[]>(
      { ok: true, command: "rank", data },
      200,
    );
  } catch (e) {
    return envelope(
      {
        ok: false,
        command: "rank",
        error: e instanceof Error ? e.message : String(e),
      },
      502,
    );
  }
}
