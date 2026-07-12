import { NextResponse } from "next/server";
import { spawn } from "child_process";
import path from "path";

import { pythonBin, repoRoot } from "@/lib/paths";
import type { ApiEnvelope } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 30;

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

function runLiveAdapt(args: string[]): Promise<unknown> {
  const py = pythonBin();
  const script = path.join(repoRoot(), "tools", "live_adapt.py");
  const cwd = repoRoot();
  return new Promise((resolve, reject) => {
    const child = spawn(py, [script, ...args, "--json"], {
      cwd,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: "1",
        PYTHONPATH: [cwd, path.join(cwd, "tools")]
          .concat(process.env.PYTHONPATH ? [process.env.PYTHONPATH] : [])
          .join(path.delimiter),
      },
    });
    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      reject(new Error("live_adapt timed out"));
    }, 15_000);
    child.stdout.on("data", (d: Buffer) => {
      stdout += d.toString();
    });
    child.stderr.on("data", (d: Buffer) => {
      stderr += d.toString();
    });
    child.on("error", (err) => {
      clearTimeout(timer);
      reject(err);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (code !== 0) {
        reject(new Error(stderr.slice(-400) || `exit ${code}`));
        return;
      }
      try {
        const start = stdout.indexOf("{");
        resolve(JSON.parse(stdout.slice(start >= 0 ? start : 0)));
      } catch (e) {
        reject(e);
      }
    });
  });
}

/** GET — adapt snapshot for desk (streak mults after paper closes). */
export async function GET() {
  try {
    const data = await runLiveAdapt(["snapshot"]);
    return envelope({ ok: true, command: "live-adapt", data }, 200);
  } catch (e) {
    return envelope(
      {
        ok: false,
        command: "live-adapt",
        error: e instanceof Error ? e.message : String(e),
      },
      502,
    );
  }
}

type Body = {
  pnl?: number;
  symbol?: string;
  model?: string;
  r?: number;
};

/** POST — record outcome (also done automatically on paper close). */
export async function POST(req: Request) {
  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    return envelope(
      { ok: false, command: "live-adapt", error: "Invalid JSON" },
      400,
    );
  }
  if (body.pnl == null || !Number.isFinite(Number(body.pnl))) {
    return envelope(
      { ok: false, command: "live-adapt", error: "pnl required" },
      400,
    );
  }
  const args = ["record", "--pnl", String(body.pnl)];
  if (body.symbol) args.push("--symbol", String(body.symbol));
  if (body.model) args.push("--model", String(body.model));
  if (body.r != null && Number.isFinite(Number(body.r))) {
    args.push("--r", String(body.r));
  }
  try {
    const data = await runLiveAdapt(args);
    return envelope({ ok: true, command: "live-adapt-record", data }, 200);
  } catch (e) {
    return envelope(
      {
        ok: false,
        command: "live-adapt",
        error: e instanceof Error ? e.message : String(e),
      },
      502,
    );
  }
}
