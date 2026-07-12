import { NextResponse } from "next/server";
import { spawn } from "child_process";
import path from "path";

import { sanitizeSymbol } from "@/lib/format";
import { pythonBin, repoRoot } from "@/lib/paths";
import type { ApiEnvelope } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

function envelope<T>(
  partial: Omit<ApiEnvelope<T>, "asof"> & { asof?: string },
  status: number,
): NextResponse {
  const body = { ...partial, asof: partial.asof ?? new Date().toISOString() };
  return NextResponse.json(body, { status });
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const symbol = sanitizeSymbol(url.searchParams.get("symbol"));

  if (!symbol) {
    return envelope(
      { ok: false, command: "live-signal", error: "symbol required" },
      400,
    );
  }

  try {
    const result = await runLiveSignal(symbol);
    return envelope({ ok: true, command: "live-signal", data: result }, 200);
  } catch (e) {
    return envelope(
      {
        ok: false,
        command: "live-signal",
        error: e instanceof Error ? e.message : String(e),
      },
      502,
    );
  }
}

function runLiveSignal(symbol: string): Promise<unknown> {
  const root = repoRoot();
  const code = `
import json, sys
sys.path.insert(0, ${JSON.stringify(root)})
sys.path.insert(0, ${JSON.stringify(path.join(root, "services"))})
from live_signal import LiveSignalEngine
print(json.dumps(LiveSignalEngine().analyze(${JSON.stringify(symbol)})))
`;

  return new Promise((resolve, reject) => {
    const child = spawn(pythonBin(), ["-c", code], {
      cwd: root,
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    });

    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      reject(new Error("timeout"));
    }, 30000);

    child.stdout.on("data", (d) => {
      stdout += d.toString();
    });
    child.stderr.on("data", (d) => {
      stderr += d.toString();
    });

    child.on("close", (code) => {
      clearTimeout(timer);
      if (code !== 0) {
        reject(new Error(stderr || `exit ${code}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout.trim()));
      } catch (e) {
        reject(new Error(`parse error: ${e}`));
      }
    });
  });
}
