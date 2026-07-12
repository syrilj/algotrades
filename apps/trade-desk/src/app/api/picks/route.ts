import { NextResponse } from "next/server";

import { isValidModelId, sanitizeSymbol } from "@/lib/format";
import { runTradeDesk } from "@/lib/tradeDesk";
import type { ApiEnvelope } from "@/lib/types";
import { SECTORS as SECTOR_LIST } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 180;

type PicksBody = {
  horizon?: string;
  model?: string;
  sectors?: string[] | string;
  symbols?: string[] | string;
  account?: number | string;
  riskPct?: number | string;
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

function parseList(v: string[] | string | undefined): string[] {
  if (v == null) return [];
  if (Array.isArray(v)) return v.map(String);
  return String(v)
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export async function POST(req: Request) {
  let body: PicksBody;
  try {
    body = (await req.json()) as PicksBody;
  } catch {
    return envelope(
      { ok: false, command: "picks", error: "Invalid JSON body" },
      400,
    );
  }

  const horizon = (body.horizon ?? "day").toLowerCase();
  if (horizon !== "day" && horizon !== "week") {
    return envelope(
      { ok: false, command: "picks", error: "horizon must be day|week" },
      400,
    );
  }

  const model =
    typeof body.model === "string" && body.model.trim()
      ? body.model.trim()
      : "auto";
  if (!isValidModelId(model)) {
    return envelope(
      { ok: false, command: "picks", error: "Invalid model id" },
      400,
    );
  }

  const args: string[] = ["picks", "--horizon", horizon, "--model", model];

  if (body.account != null && body.account !== "") {
    const account = Number(body.account);
    if (!Number.isFinite(account) || account <= 0) {
      return envelope(
        { ok: false, command: "picks", error: "Invalid account" },
        400,
      );
    }
    args.push("--account", String(account));
  }

  if (body.riskPct != null && body.riskPct !== "") {
    const riskPct = Number(body.riskPct);
    if (!Number.isFinite(riskPct) || riskPct <= 0 || riskPct > 100) {
      return envelope(
        { ok: false, command: "picks", error: "Invalid riskPct" },
        400,
      );
    }
    args.push("--risk-pct", String(riskPct));
  }

  const sectors = parseList(body.sectors);
  if (sectors.length) {
    const allowed = new Set<string>(SECTOR_LIST as unknown as string[]);
    for (const s of sectors) {
      if (!allowed.has(s)) {
        return envelope(
          { ok: false, command: "picks", error: `Unknown sector: ${s}` },
          400,
        );
      }
    }
    args.push("--sectors", sectors.join(","));
  }

  const symbolsRaw = parseList(body.symbols);
  if (symbolsRaw.length) {
    const symbols: string[] = [];
    for (const raw of symbolsRaw) {
      const sym = sanitizeSymbol(raw);
      if (!sym) {
        return envelope(
          {
            ok: false,
            command: "picks",
            error: `Invalid symbol: ${raw}`,
          },
          400,
        );
      }
      symbols.push(sym);
    }
    args.push("--symbols", symbols.join(","));
  }

  try {
    const data = await runTradeDesk(args);
    return envelope({ ok: true, command: "picks", data }, 200);
  } catch (e) {
    return envelope(
      {
        ok: false,
        command: "picks",
        error: e instanceof Error ? e.message : String(e),
      },
      502,
    );
  }
}
