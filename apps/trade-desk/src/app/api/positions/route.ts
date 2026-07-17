import { NextResponse } from "next/server";

import { runPaperLedger } from "@/lib/tradeDesk";
import type {
  ApiEnvelope,
  LedgerStatsRow,
  PaperPosition,
  PositionsResponse,
} from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 90;


const ID_RE = /^t_[A-Za-z0-9_]+$/;

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

function extractPositions(raw: unknown): PaperPosition[] {
  const rec = raw as { positions?: PaperPosition[] };
  return Array.isArray(rec?.positions) ? rec.positions : [];
}

function extractStats(raw: unknown): PositionsResponse["stats"] {
  const rec = raw as {
    rows?: LedgerStatsRow[];
    overall?: Partial<LedgerStatsRow>;
  };
  return {
    rows: Array.isArray(rec?.rows) ? rec.rows : [],
    overall: rec?.overall,
  };
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const statusParam = url.searchParams.get("status") || "all";
  const status =
    statusParam === "open" ||
    statusParam === "closed" ||
    statusParam === "cancelled" ||
    statusParam === "all"
      ? statusParam
      : "all";
  const shouldMark = url.searchParams.get("mark") === "1";

  try {
    let marked = false;
    if (shouldMark) {
      await runPaperLedger(["mark"], 60_000);
      marked = true;
    }

    const [listRaw, statsRaw] = await Promise.all([
      runPaperLedger(["list", "--status", status], 30_000),
      runPaperLedger(["stats"], 30_000),
    ]);

    const positions = extractPositions(listRaw);
    const stats = extractStats(statsRaw);
    const listRec = listRaw as { asof?: string };
    const statsRec = statsRaw as { asof?: string };
    const asof =
      statsRec.asof ?? listRec.asof ?? new Date().toISOString();

    const data: PositionsResponse = { positions, stats, marked, asof };
    return envelope<PositionsResponse>(
      { ok: true, command: "positions", data, asof },
      200,
    );
  } catch (e) {
    return envelope(
      {
        ok: false,
        command: "positions",
        error: e instanceof Error ? e.message : String(e),
      },
      502,
    );
  }
}

type PostBody = {
  action?: "close" | "cancel" | "delete" | "update";
  id?: string;
  exit?: number;
  reason?: string;
  shares?: number;
  entry?: number;
  stop?: number;
  notes?: string;
};

export async function POST(req: Request) {
  let body: PostBody;
  try {
    body = (await req.json()) as PostBody;
  } catch {
    return envelope(
      { ok: false, command: "positions", error: "Invalid JSON body" },
      400,
    );
  }

  const action = body.action;
  if (action !== "close" && action !== "cancel" && action !== "delete" && action !== "update") {
    return envelope(
      { ok: false, command: "positions", error: "Unsupported action" },
      400,
    );
  }

  const id = typeof body.id === "string" ? body.id.trim() : "";
  if (!id || !ID_RE.test(id)) {
    return envelope(
      { ok: false, command: "positions", error: "Invalid position id" },
      400,
    );
  }

  try {
    if (action === "close") {
      const exit = Number(body.exit);
      if (!Number.isFinite(exit) || exit <= 0) {
        return envelope(
          { ok: false, command: "positions", error: "Invalid exit price" },
          400,
        );
      }

      const reason =
        typeof body.reason === "string" && body.reason.trim()
          ? body.reason.trim()
          : "manual";

      const raw = (await runPaperLedger(
        ["close", "--id", id, "--exit", String(exit), "--reason", reason],
        20_000,
      )) as { ok?: boolean; position?: PaperPosition; error?: string };
      if (raw?.ok === false) {
        throw new Error(raw.error || "close failed");
      }
      const position = raw.position;
      if (!position) {
        throw new Error("close returned no position");
      }
      return envelope<{ position: PaperPosition }>(
        { ok: true, command: "positions", data: { position } },
        200,
      );
    } else if (action === "cancel") {
      const reason =
        typeof body.reason === "string" && body.reason.trim()
          ? body.reason.trim()
          : "cancel";

      const raw = (await runPaperLedger(
        ["cancel", "--id", id, "--reason", reason],
        20_000,
      )) as { ok?: boolean; position?: PaperPosition; error?: string };
      if (raw?.ok === false) {
        throw new Error(raw.error || "cancel failed");
      }
      const position = raw.position;
      if (!position) {
        throw new Error("cancel returned no position");
      }
      return envelope<{ position: PaperPosition }>(
        { ok: true, command: "positions", data: { position } },
        200,
      );
    } else if (action === "delete") {
      const raw = (await runPaperLedger(
        ["delete", "--id", id],
        20_000,
      )) as { ok?: boolean; error?: string };
      if (raw?.ok === false) {
        throw new Error(raw.error || "delete failed");
      }
      return envelope<{ success: boolean }>(
        { ok: true, command: "positions", data: { success: true } },
        200,
      );
    } else if (action === "update") {
      const args = ["update", "--id", id];
      if (body.shares != null) {
        const shares = Number(body.shares);
        if (!Number.isInteger(shares) || shares <= 0) {
          return envelope({ ok: false, command: "positions", error: "Invalid shares" }, 400);
        }
        args.push("--shares", String(shares));
      }
      if (body.entry != null) {
        const entry = Number(body.entry);
        if (!Number.isFinite(entry) || entry <= 0) {
          return envelope({ ok: false, command: "positions", error: "Invalid entry price" }, 400);
        }
        args.push("--entry", String(entry));
      }
      if (body.stop != null) {
        const stop = Number(body.stop);
        if (!Number.isFinite(stop) || stop <= 0) {
          return envelope({ ok: false, command: "positions", error: "Invalid stop price" }, 400);
        }
        args.push("--stop", String(stop));
      }
      if (typeof body.notes === "string" && body.notes.trim()) {
        args.push("--notes", body.notes.trim());
      }

      const raw = (await runPaperLedger(args, 20_000)) as { ok?: boolean; position?: PaperPosition; error?: string };
      if (raw?.ok === false) {
        throw new Error(raw.error || "update failed");
      }
      const position = raw.position;
      if (!position) {
        throw new Error("update returned no position");
      }
      return envelope<{ position: PaperPosition }>(
        { ok: true, command: "positions", data: { position } },
        200,
      );
    }
  } catch (e) {
    return envelope(
      {
        ok: false,
        command: "positions",
        error: e instanceof Error ? e.message : String(e),
      },
      502,
    );
  }
}

