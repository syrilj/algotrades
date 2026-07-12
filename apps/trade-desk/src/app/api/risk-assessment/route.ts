import { NextResponse } from "next/server";

import { runRiskAssessment } from "@/lib/tradeDesk";
import type { ApiEnvelope, RiskAssessmentResponse } from "@/lib/types";

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

function asNumberList(value: unknown): number[] {
  if (Array.isArray(value)) {
    return value.map((v) => Number(v)).filter((n) => Number.isFinite(n));
  }
  if (typeof value === "string" && value.trim()) {
    return value
      .split(",")
      .map((s) => Number(s.trim()))
      .filter((n) => Number.isFinite(n));
  }
  return [];
}

function asPositions(value: unknown): unknown[] | undefined {
  if (Array.isArray(value)) {
    return value.filter((p) => p && typeof p === "object");
  }
  if (typeof value === "string" && value.trim()) {
    try {
      const parsed = JSON.parse(value);
      if (Array.isArray(parsed)) {
        return parsed.filter((p) => p && typeof p === "object");
      }
    } catch {
      return undefined;
    }
  }
  return undefined;
}

export async function POST(req: Request) {
  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return envelope({ ok: false, command: "risk-assessment", error: "Invalid JSON" }, 400);
  }

  const account = Number(body.account);
  if (!Number.isFinite(account) || account <= 0) {
    return envelope(
      { ok: false, command: "risk-assessment", error: "account must be positive" },
      400,
    );
  }

  const equity = body.equity != null ? Number(body.equity) : account;
  const peak = body.peak != null ? Number(body.peak) : Math.max(account, equity);
  if (!Number.isFinite(equity) || equity <= 0) {
    return envelope(
      { ok: false, command: "risk-assessment", error: "equity must be positive" },
      400,
    );
  }
  if (!Number.isFinite(peak) || peak <= 0) {
    return envelope(
      { ok: false, command: "risk-assessment", error: "peak must be positive" },
      400,
    );
  }

  const confidence =
    body.confidence != null ? Number(body.confidence) : 0.95;
  if (!Number.isFinite(confidence) || confidence <= 0 || confidence >= 1) {
    return envelope(
      { ok: false, command: "risk-assessment", error: "confidence must be 0-1" },
      400,
    );
  }

  const holdingDays = body.holding_days != null ? Number(body.holding_days) : 1;
  if (!Number.isFinite(holdingDays) || holdingDays < 1) {
    return envelope(
      { ok: false, command: "risk-assessment", error: "holding_days must be >= 1" },
      400,
    );
  }

  const riskFree = body.risk_free != null ? Number(body.risk_free) : 0.04;
  if (!Number.isFinite(riskFree)) {
    return envelope(
      { ok: false, command: "risk-assessment", error: "risk_free must be a number" },
      400,
    );
  }

  const stopLoss = body.stop_loss_dollars != null ? Number(body.stop_loss_dollars) : 0;
  const riskPct = body.risk_pct != null ? Number(body.risk_pct) : 0.01;

  const returns = asNumberList(body.returns);
  const closedPnl = asNumberList(body.closed_pnl);
  const positions = asPositions(body.positions);

  const payload: Record<string, unknown> = {
    account,
    equity,
    peak,
    confidence,
    holding_days: holdingDays,
    risk_free: riskFree,
    returns,
    closed_pnl: closedPnl,
    stop_loss_dollars: stopLoss,
    risk_pct: riskPct,
  };
  if (positions) {
    payload.positions = positions;
  }

  try {
    const raw = await runRiskAssessment(payload, 30_000);
    return envelope<RiskAssessmentResponse>(
      { ok: true, command: "risk-assessment", data: raw as RiskAssessmentResponse },
      200,
    );
  } catch (e) {
    return envelope(
      {
        ok: false,
        command: "risk-assessment",
        error: e instanceof Error ? e.message : String(e),
      },
      502,
    );
  }
}
