import fs from "fs/promises";
import path from "path";

import { NextResponse } from "next/server";

import { isValidModelId } from "@/lib/format";
import { modelsRoot } from "@/lib/paths";
import { loadModelDetail } from "@/lib/tradeDesk";
import type { ApiEnvelope } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type ModelDetail = Awaited<ReturnType<typeof loadModelDetail>>;

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

export async function GET(
  _req: Request,
  ctx: { params: Promise<{ id: string }> },
) {
  const { id: rawId } = await ctx.params;
  const id = decodeURIComponent(rawId ?? "").trim();

  if (!id || !isValidModelId(id) || id === "auto") {
    return envelope(
      { ok: false, command: "models/[id]", error: "Invalid model id" },
      400,
    );
  }

  const dir = path.join(modelsRoot(), id);
  try {
    const st = await fs.stat(dir);
    if (!st.isDirectory()) {
      return envelope(
        { ok: false, command: "models/[id]", error: "Model not found" },
        404,
      );
    }
  } catch {
    return envelope(
      { ok: false, command: "models/[id]", error: "Model not found" },
      404,
    );
  }

  try {
    const data = await loadModelDetail(id);
    return envelope<ModelDetail>(
      { ok: true, command: "models/[id]", data },
      200,
    );
  } catch (e) {
    return envelope(
      {
        ok: false,
        command: "models/[id]",
        error: e instanceof Error ? e.message : String(e),
      },
      502,
    );
  }
}
