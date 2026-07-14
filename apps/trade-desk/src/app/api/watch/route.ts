import { NextResponse } from "next/server";

import { normalizeAnalyze } from "@/lib/analyzeNormalize";
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
  /** Full analyze payload (state + plan + model) for the board. */
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
 *
 * IMPORTANT: runTradeDesk() already returns the analyze object (state/plan/model).
 * Do not read `.data` on that object — it is undefined and emptied the board.
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
    if (!Number.isFinite(riskPct) || riskPct <= 0 || riskPct > 5) {
      return envelope(
        { ok: false, command: "watch", error: "Invalid riskPct (percent points, 0–5]" },
        400,
      );
    }
    // UI speaks percent points; Python --risk-pct is a fraction.
    shared.push("--risk-pct", String(riskPct / 100));
  }

  // interval accepted for API compatibility; analyze uses period/defaults.
  void body.interval;

  const settled = await Promise.allSettled(
    symbols.map(async (symbol) => {
      const raw = await runTradeDesk([symbol, ...shared]);
      const data = normalizeAnalyze(raw);
      // Prefer symbol on state for board row extraction
      if (data.state && !data.state.symbol) {
        data.state.symbol = symbol;
      }
      return { symbol, data };
    }),
  );

  const snapshots: WatchSnapshot[] = settled.map((r, i) => {
    const symbol = symbols[i]!;
    if (r.status === "fulfilled") {
      // r.value = { symbol, data: AnalyzeResponse } — attach full analyze payload
      return { symbol, ok: true, data: r.value.data };
    }
    return {
      symbol,
      ok: false,
      error: r.reason instanceof Error ? r.reason.message : String(r.reason),
    };
  });

  const anyOk = snapshots.some((s) => s.ok);
  const failed = snapshots.filter((s) => !s.ok).map((s) => s.symbol);
  return envelope(
    {
      ok: anyOk,
      command: "watch",
      data: { symbols, model, snapshots },
      error: anyOk
        ? failed.length
          ? `Partial: failed ${failed.join(", ")}`
          : undefined
        : "All symbol analyzes failed",
    },
    anyOk ? 200 : 502,
  );
}
