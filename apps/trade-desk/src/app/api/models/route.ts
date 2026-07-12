import fs from "fs/promises";
import path from "path";

import { NextResponse } from "next/server";

import { isValidModelId } from "@/lib/format";
import { modelsRoot } from "@/lib/paths";
import { loadModelDetail, loadModelsCatalog } from "@/lib/tradeDesk";
import type { ApiEnvelope, ModelsCatalog } from "@/lib/types";

type ModelDetail = Awaited<ReturnType<typeof loadModelDetail>>;

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

/** Catalog + single-model detail. Query `?id=<model>` returns a model detail. */
export async function GET(req: Request) {
  const url = new URL(req.url);
  const id = url.searchParams.get("id")?.trim();

  if (id) {
    if (!isValidModelId(id) || id === "auto") {
      return envelope(
        { ok: false, command: "models", error: "Invalid model id" },
        400,
      );
    }

    const dir = path.join(modelsRoot(), id);
    try {
      const st = await fs.stat(dir);
      if (!st.isDirectory()) {
        return envelope(
          { ok: false, command: "models", error: "Model not found" },
          404,
        );
      }
    } catch {
      return envelope(
        { ok: false, command: "models", error: "Model not found" },
        404,
      );
    }

    try {
      const data = await loadModelDetail(id);
      return envelope<ModelDetail>(
        { ok: true, command: "models", data },
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
