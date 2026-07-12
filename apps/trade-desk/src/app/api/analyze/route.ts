import { NextResponse } from "next/server";

import { normalizeAnalyze } from "@/lib/analyzeNormalize";
import { isValidModelId, sanitizeSymbol } from "@/lib/format";
import { runTradeDesk } from "@/lib/tradeDesk";
import type { AnalyzeResponse, ApiEnvelope } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 120;

type AnalyzeBody = {
  symbol?: string;
  account?: number | string;
  riskPct?: number | string;
  risk_pct?: number | string;
  model?: string;
  period?: string;
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
  let body: AnalyzeBody;
  try {
    body = (await req.json()) as AnalyzeBody;
  } catch {
    return envelope(
      { ok: false, command: "analyze", error: "Invalid JSON body" },
      400,
    );
  }

  const symbol = sanitizeSymbol(body.symbol);
  if (!symbol) {
    return envelope(
      {
        ok: false,
        command: "analyze",
        error: "symbol required (alphanumeric)",
      },
      400,
    );
  }

  const model =
    typeof body.model === "string" && body.model.trim()
      ? body.model.trim()
      : "auto";
  if (!isValidModelId(model)) {
    return envelope(
      { ok: false, command: "analyze", error: "Invalid model id" },
      400,
    );
  }

  const args: string[] = [symbol];

  if (body.account != null && body.account !== "") {
    const account = Number(body.account);
    if (!Number.isFinite(account) || account <= 0) {
      return envelope(
        { ok: false, command: "analyze", error: "Invalid account" },
        400,
      );
    }
    args.push("--account", String(account));
  }

  const riskPctRaw = body.riskPct ?? body.risk_pct;
  if (riskPctRaw != null && riskPctRaw !== "") {
    const riskPct = Number(riskPctRaw);
    if (!Number.isFinite(riskPct) || riskPct <= 0 || riskPct > 100) {
      return envelope(
        { ok: false, command: "analyze", error: "Invalid riskPct" },
        400,
      );
    }
    args.push("--risk-pct", String(riskPct));
  }

  args.push("--model", model);

  if (typeof body.period === "string" && body.period.trim()) {
    const period = body.period.trim();
    if (!/^[a-zA-Z0-9]+$/.test(period)) {
      return envelope(
        { ok: false, command: "analyze", error: "Invalid period" },
        400,
      );
    }
    args.push("--period", period);
  }

  try {
    const raw = await runTradeDesk(args);
    const data = normalizeAnalyze(raw);
    const asof =
      (typeof data?.state?.asof === "string" && data.state.asof) ||
      new Date().toISOString();
    return envelope<AnalyzeResponse>(
      { ok: true, command: "analyze", data, asof },
      200,
    );
  } catch (e) {
    return envelope(
      {
        ok: false,
        command: "analyze",
        error: e instanceof Error ? e.message : String(e),
      },
      502,
    );
  }
}
