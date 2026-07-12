import { NextResponse } from "next/server";

import { isValidModelId, sanitizeSymbol } from "@/lib/format";
import { runTradeDesk } from "@/lib/tradeDesk";
import type { AnalyzeResponse, ApiEnvelope, PlainPlan } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 120;

type AnalyzeBody = {
  symbol?: string;
  account?: number | string;
  riskPct?: number | string;
  model?: string;
  period?: string;
};

function derivePlan(state: AnalyzeResponse["state"]): PlainPlan | undefined {
  const action = ((): PlainPlan["action"] => {
    if (state.breakout_buy) return "BUY NOW";
    if (state.breakout_ready) return "BUY BREAKOUT";
    if (state.setup_ok && state.entry != null) return "BUY NOW";
    if (state.setup_kind === "avoid" || state.hard_gates_ok === false) {
      return "AVOID";
    }
    if (state.breakout_level != null && state.price != null) {
      return state.price < state.breakout_level ? "BREAKOUT WATCH" : "PULLBACK ZONE";
    }
    return "WAIT";
  })();

  const why =
    state.setup_kind && state.setup_kind !== "none"
      ? `setup: ${state.setup_kind} · conf ${((state.confidence ?? 0) * 100).toFixed(0)}%`
      : `confidence ${((state.confidence ?? 0) * 100).toFixed(0)}% · ${state.missing?.length ? `${state.missing.length} gate(s) missing` : "all gates clear"}`;

  const doNext =
    action === "BUY NOW"
      ? `Enter ${state.entry ? `near ${state.entry.toFixed(2)}` : "at market"}, stop ${state.stop?.toFixed(2) ?? "—"}, trail ${state.trail_arm?.toFixed(2) ?? "—"}.`
      : action === "BUY BREAKOUT"
        ? `Buy a break above ${state.breakout_level?.toFixed(2) ?? "—"}, stop ${state.stop?.toFixed(2) ?? "—"}.`
        : action === "BREAKOUT WATCH"
          ? `Watch for a break above ${state.breakout_level?.toFixed(2) ?? "—"}.`
          : action === "PULLBACK ZONE"
            ? `Wait for a pullback toward entry ${state.entry?.toFixed(2) ?? "—"}.`
            : action === "AVOID"
              ? `Gates not met. Avoid or wait for a reset.`
              : `Conditions not fully aligned. Monitor for a clearer setup.`;

  return {
    action,
    why,
    do_next: doNext,
    confidence_note: state.missing?.length
      ? `missing: ${state.missing.join(", ")}`
      : undefined,
  };
}

function normalizeAnalyze(data: unknown): AnalyzeResponse {
  const d = data as Record<string, unknown>;
  if (d.sizing != null && d.size == null) {
    d.size = d.sizing;
  }
  const state = (d.state ?? {}) as AnalyzeResponse["state"];
  if (d.plan == null) {
    d.plan = derivePlan(state);
  }
  return d as AnalyzeResponse;
}

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

  if (body.riskPct != null && body.riskPct !== "") {
    const riskPct = Number(body.riskPct);
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
