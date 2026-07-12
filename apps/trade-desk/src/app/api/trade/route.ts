import { NextResponse } from "next/server";

import { isValidModelId, sanitizeSymbol } from "@/lib/format";
import { runPaperLedger } from "@/lib/tradeDesk";
import type { ApiEnvelope, PaperPosition, TradeTicketInput } from "@/lib/types";

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

function posNum(v: unknown): number | null {
  const n = Number(v);
  if (!Number.isFinite(n) || n <= 0) return null;
  return n;
}

export async function POST(req: Request) {
  let body: TradeTicketInput;
  try {
    body = (await req.json()) as TradeTicketInput;
  } catch {
    return envelope(
      { ok: false, command: "trade", error: "Invalid JSON body" },
      400,
    );
  }

  const symbol = sanitizeSymbol(body.symbol);
  if (!symbol) {
    return envelope(
      { ok: false, command: "trade", error: "Invalid symbol" },
      400,
    );
  }

  const side = body.side;
  if (side !== "long" && side !== "short") {
    return envelope(
      { ok: false, command: "trade", error: "side must be long or short" },
      400,
    );
  }

  const shares = Number(body.shares);
  if (!Number.isInteger(shares) || shares <= 0) {
    return envelope(
      { ok: false, command: "trade", error: "Invalid shares" },
      400,
    );
  }

  const entry = posNum(body.entry);
  const stop = posNum(body.stop);
  if (entry == null || stop == null) {
    return envelope(
      { ok: false, command: "trade", error: "Invalid entry or stop" },
      400,
    );
  }

  const model = typeof body.model === "string" ? body.model.trim() : "";
  if (!model || !isValidModelId(model)) {
    return envelope(
      { ok: false, command: "trade", error: "Invalid model id" },
      400,
    );
  }

  const args = [
    "open",
    "--symbol",
    symbol,
    "--side",
    side,
    "--shares",
    String(shares),
    "--entry",
    String(entry),
    "--stop",
    String(stop),
    "--model",
    model,
    "--source",
    "verdict_panel",
  ];

  if (body.trailArm != null && Number.isFinite(body.trailArm)) {
    args.push("--trail-arm", String(body.trailArm));
  }
  if (body.account != null) {
    const account = Number(body.account);
    if (Number.isFinite(account) && account > 0) {
      args.push("--account", String(account));
    }
  }
  if (body.riskPct != null) {
    const riskPct = Number(body.riskPct);
    if (Number.isFinite(riskPct) && riskPct > 0) {
      args.push("--risk-pct", String(riskPct));
    }
  }
  if (body.dollarRisk != null) {
    const dollarRisk = Number(body.dollarRisk);
    if (Number.isFinite(dollarRisk) && dollarRisk > 0) {
      args.push("--dollar-risk", String(dollarRisk));
    }
  }
  if (typeof body.action === "string" && body.action.trim()) {
    args.push("--action", body.action.trim());
  }
  if (body.confidence != null && Number.isFinite(body.confidence)) {
    args.push("--confidence", String(body.confidence));
  }
  if (body.override) {
    args.push("--override");
  }
  if (typeof body.reason === "string" && body.reason.trim()) {
    args.push("--reason", body.reason.trim());
  }

  try {
    const raw = (await runPaperLedger(args, 20_000)) as {
      ok?: boolean;
      position?: PaperPosition;
      error?: string;
    };
    if (raw?.ok === false) {
      throw new Error(raw.error || "paper ledger open failed");
    }
    const position = raw.position;
    if (!position) {
      throw new Error("paper ledger returned no position");
    }
    return envelope<{ position: PaperPosition }>(
      { ok: true, command: "trade", data: { position } },
      200,
    );
  } catch (e) {
    return envelope(
      {
        ok: false,
        command: "trade",
        error: e instanceof Error ? e.message : String(e),
      },
      502,
    );
  }
}
