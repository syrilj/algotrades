import { NextResponse } from "next/server";

import { loadModelsCatalog } from "@/lib/tradeDesk";
import type { ApiEnvelope, ModelsCatalog } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

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

/** Dynamic catalog: new v* folders with signal_engine.py appear via loadModelsCatalog. */
export async function GET() {
  try {
    const data = await loadModelsCatalog();
    return envelope<ModelsCatalog>(
      {
        ok: true,
        command: "models",
        data,
        asof: data.updated_at ?? undefined,
      },
      200,
    );
  } catch (e) {
    return envelope(
      {
        ok: false,
        command: "models",
        error: e instanceof Error ? e.message : String(e),
      },
      502,
    );
  }
}
