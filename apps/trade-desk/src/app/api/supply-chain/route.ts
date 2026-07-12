import { NextResponse } from "next/server";

import { sanitizeSymbol } from "@/lib/format";
import { runSupplyChain } from "@/lib/tradeDesk";
import type { ApiEnvelope, SupplyChainResponse } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 120;

type SupplyChainBody = {
  symbol?: string;
  account?: number | string;
  riskPct?: number | string;
  risk_pct?: number | string;
  model?: string;
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
  let body: SupplyChainBody;
  try {
    body = (await req.json()) as SupplyChainBody;
  } catch {
    return envelope({ ok: false, command: "supply_chain", error: "Invalid JSON body" }, 400);
  }

  const symbol = sanitizeSymbol(body.symbol);
  if (!symbol) {
    return envelope(
      { ok: false, command: "supply_chain", error: "symbol required (alphanumeric)" },
      400,
    );
  }

  const args = [symbol];

  if (body.account != null && body.account !== "") {
    const account = Number(body.account);
    if (!Number.isFinite(account) || account <= 0) {
      return envelope({ ok: false, command: "supply_chain", error: "Invalid account" }, 400);
    }
    args.push("--account", String(account));
  }

  const riskPctRaw = body.riskPct ?? body.risk_pct;
  if (riskPctRaw != null && riskPctRaw !== "") {
    const riskPct = Number(riskPctRaw);
    if (!Number.isFinite(riskPct) || riskPct <= 0 || riskPct > 100) {
      return envelope({ ok: false, command: "supply_chain", error: "Invalid riskPct" }, 400);
    }
    args.push("--risk-pct", String(riskPct));
  }

  if (typeof body.model === "string" && body.model.trim()) {
    const model = body.model.trim();
    if (!/^[a-zA-Z0-9_]+$/.test(model)) {
      return envelope({ ok: false, command: "supply_chain", error: "Invalid model" }, 400);
    }
    args.push("--model", model);
  }

  try {
    const raw = await runSupplyChain(args);
    const data = raw as SupplyChainResponse;
    const asof = data?.asof ?? new Date().toISOString();
    return envelope<SupplyChainResponse>(
      { ok: true, command: "supply_chain", data, asof },
      200,
    );
  } catch (e) {
    return envelope(
      {
        ok: false,
        command: "supply_chain",
        error: e instanceof Error ? e.message : String(e),
      },
      502,
    );
  }
}
