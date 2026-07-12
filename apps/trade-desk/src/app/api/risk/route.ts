import { NextResponse } from "next/server";

import { sanitizeSymbol } from "@/lib/format";
import { runRiskManager } from "@/lib/tradeDesk";
import type { ApiEnvelope } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

function envelope<T>(
  partial: Omit<ApiEnvelope<T>, "asof"> & { asof?: string },
  status: number,
): NextResponse {
  return NextResponse.json(
    { ...partial, asof: partial.asof ?? new Date().toISOString() },
    { status },
  );
}

/** Lightweight risk_manager plan/status/check-open for UI widgets. */
export async function POST(req: Request) {
  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return envelope({ ok: false, command: "risk", error: "Invalid JSON" }, 400);
  }

  const cmd = String(body.cmd || "plan");
  const args: string[] = [cmd];

  if (cmd === "plan") {
    const symbol = sanitizeSymbol(body.symbol);
    if (!symbol) {
      return envelope(
        { ok: false, command: "risk", error: "symbol required" },
        400,
      );
    }
    args.push("--symbol", symbol);
    if (body.account != null) args.push("--account", String(body.account));
    if (body.peak != null) args.push("--peak", String(body.peak));
    if (body.conf != null) args.push("--conf", String(body.conf));
    if (body.vol_z != null) args.push("--vol-z", String(body.vol_z));
    if (body.qqq_ok) args.push("--qqq-ok");
    if (body.defensive) args.push("--defensive");
    if (body.no_options) args.push("--no-options");
    if (typeof body.history === "string" && body.history) {
      args.push("--history", body.history);
    }
  } else if (cmd === "status") {
    if (body.equity == null || body.peak == null) {
      return envelope(
        { ok: false, command: "risk", error: "equity and peak required" },
        400,
      );
    }
    args.push("--equity", String(body.equity), "--peak", String(body.peak));
    if (typeof body.history === "string" && body.history) {
      args.push("--history", body.history);
    }
  } else if (cmd === "check-open") {
    if (body.entry == null) {
      return envelope(
        { ok: false, command: "risk", error: "entry required" },
        400,
      );
    }
    args.push("--entry", String(body.entry));
    if (body.vehicle) args.push("--vehicle", String(body.vehicle));
    if (body.symbol) args.push("--symbol", String(body.symbol));
    if (body.current != null) args.push("--current", String(body.current));
    if (body.pnl_pct != null) args.push("--pnl-pct", String(body.pnl_pct));
    if (body.peak_px != null) args.push("--peak-px", String(body.peak_px));
    if (body.sessions != null) args.push("--sessions", String(body.sessions));
    if (body.dte != null) args.push("--dte", String(body.dte));
  } else if (cmd === "policy") {
    // no extra args
  } else {
    return envelope(
      { ok: false, command: "risk", error: `unknown cmd ${cmd}` },
      400,
    );
  }

  try {
    const data = await runRiskManager(args);
    return envelope({ ok: true, command: `risk-${cmd}`, data }, 200);
  } catch (e) {
    return envelope(
      {
        ok: false,
        command: `risk-${cmd}`,
        error: e instanceof Error ? e.message : String(e),
      },
      502,
    );
  }
}
