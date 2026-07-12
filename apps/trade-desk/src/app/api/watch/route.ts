import { NextResponse } from "next/server";

import { isValidModelId, sanitizeSymbol } from "@/lib/format";
import { runTradeDesk } from "@/lib/tradeDesk";
import type { AnalyzeResponse, ApiEnvelope } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 180;

const MAX_SYMBOLS = 18;

type WatchBody = {
  symbols?: string[] | string;
  model?: string;
  interval?: string;
  account?: number | string;
  riskPct?: number | string;
};

type WatchSnapshot = {
  symbol: string;
  ok: boolean;
  data?: AnalyzeResponse;
  error?: string;
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

function parseSymbols(v: string[] | string | undefined): string[] {
  if (v == null) return [];
  if (Array.isArray(v)) return v.map(String);
  return String(v)
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

/**
 * Watch CLI is a live TTY loop and does not emit reliable --json snapshots.
 * Fan-out: one analyze call per symbol (capped), return array of snapshots.
 */
export async function POST(req: Request) {
  let body: WatchBody;
  try {
    body = (await req.json()) as WatchBody;
  } catch {
    return envelope(
      { ok: false, command: "watch", error: "Invalid JSON body" },
      400,
    );
  }

  const rawList = parseSymbols(body.symbols);
  if (!rawList.length) {
    return envelope(
      { ok: false, command: "watch", error: "symbols required" },
      400,
    );
  }
  if (rawList.length > MAX_SYMBOLS) {
    return envelope(
      {
        ok: false,
        command: "watch",
        error: `Max ${MAX_SYMBOLS} symbols per request`,
      },
      400,
    );
  }

  const symbols: string[] = [];
  for (const raw of rawList) {
    const sym = sanitizeSymbol(raw);
    if (!sym) {
      return envelope(
        { ok: false, command: "watch", error: `Invalid symbol: ${raw}` },
        400,
      );
    }
    symbols.push(sym);
  }

  const model =
    typeof body.model === "string" && body.model.trim()
      ? body.model.trim()
      : "auto";
  if (!isValidModelId(model)) {
    return envelope(
      { ok: false, command: "watch", error: "Invalid model id" },
      400,
    );
  }

  const shared: string[] = ["--model", model];

  if (body.account != null && body.account !== "") {
    const account = Number(body.account);
    if (!Number.isFinite(account) || account <= 0) {
      return envelope(
        { ok: false, command: "watch", error: "Invalid account" },
        400,
      );
    }
    shared.push("--account", String(account));
  }

  if (body.riskPct != null && body.riskPct !== "") {
    const riskPct = Number(body.riskPct);
    if (!Number.isFinite(riskPct) || riskPct <= 0 || riskPct > 100) {
      return envelope(
        { ok: false, command: "watch", error: "Invalid riskPct" },
        400,
      );
    }
    shared.push("--risk-pct", String(riskPct));
  }

  // interval accepted for API compatibility; analyze uses period/defaults.
  void body.interval;

  const settled = await Promise.allSettled(
    symbols.map(async (symbol) => {
      const data = (await runTradeDesk([
        symbol,
        ...shared,
      ])) as AnalyzeResponse;
      return { symbol, data };
    }),
  );

  const snapshots: WatchSnapshot[] = settled.map((r, i) => {
    const symbol = symbols[i]!;
    if (r.status === "fulfilled") {
      return { symbol, ok: true, data: r.value.data };
    }
    return {
      symbol,
      ok: false,
      error: r.reason instanceof Error ? r.reason.message : String(r.reason),
    };
  });

  const anyOk = snapshots.some((s) => s.ok);
  return envelope(
    {
      ok: anyOk,
      command: "watch",
      data: { symbols, model, snapshots },
      error: anyOk ? undefined : "All symbol analyzes failed",
    },
    anyOk ? 200 : 502,
  );
}
