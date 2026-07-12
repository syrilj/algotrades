import { NextResponse } from "next/server";
import { spawn } from "child_process";
import path from "path";

import { isValidModelId } from "@/lib/format";
import { pythonBin, repoRoot } from "@/lib/paths";
import type { ApiEnvelope } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 300;

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

type Body = {
  account?: number | string;
  riskPct?: number | string;
  model?: string;
  top?: number | string;
  deep?: number | string;
  universe?: "open" | "full";
  fast?: boolean;
};

function runOpenScan(args: string[]): Promise<unknown> {
  const py = pythonBin();
  const script = path.join(repoRoot(), "tools", "open_scan.py");
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
      reject(new Error("open_scan timed out after 280s"));
    }, 280_000);
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
        reject(
          new Error(
            `open_scan exit ${code}: ${stderr.slice(-600) || stdout.slice(-300)}`,
          ),
        );
        return;
      }
      try {
        const start = Math.min(
          ...[stdout.indexOf("{"), stdout.indexOf("[")].filter((i) => i >= 0),
        );
        resolve(JSON.parse(stdout.slice(Number.isFinite(start) ? start : 0)));
      } catch (e) {
        reject(
          new Error(
            `JSON parse failed: ${(e as Error).message}. tail: ${stdout.slice(-200)}`,
          ),
        );
      }
    });
  });
}

/** GET — last saved open scan if present (fast). */
export async function GET() {
  try {
    const fs = await import("fs/promises");
    const p = path.join(repoRoot(), "runs", "live_adapt", "LAST_OPEN_SCAN.json");
    const raw = await fs.readFile(p, "utf8");
    const data = JSON.parse(raw);
    return envelope({ ok: true, command: "open-scan-cached", data }, 200);
  } catch {
    return envelope(
      {
        ok: false,
        command: "open-scan-cached",
        error: "No cached scan yet — POST /api/open-scan to run one",
      },
      404,
    );
  }
}

/** POST — run market open scanner (VPA → WINNER deep). */
export async function POST(req: Request) {
  let body: Body = {};
  try {
    body = (await req.json()) as Body;
  } catch {
    body = {};
  }

  const model =
    typeof body.model === "string" && body.model.trim()
      ? body.model.trim()
      : "auto";
  if (!isValidModelId(model)) {
    return envelope(
      { ok: false, command: "open-scan", error: "Invalid model" },
      400,
    );
  }

  const args: string[] = ["--model", model];
  if (body.account != null && body.account !== "") {
    const account = Number(body.account);
    if (!Number.isFinite(account) || account <= 0) {
      return envelope(
        { ok: false, command: "open-scan", error: "Invalid account" },
        400,
      );
    }
    args.push("--account", String(account));
  }
  if (body.riskPct != null && body.riskPct !== "") {
    const riskPct = Number(body.riskPct);
    if (!Number.isFinite(riskPct) || riskPct <= 0) {
      return envelope(
        { ok: false, command: "open-scan", error: "Invalid riskPct" },
        400,
      );
    }
    args.push("--risk-pct", String(riskPct));
  }
  if (body.top != null) args.push("--top", String(Number(body.top) || 12));
  if (body.deep != null) args.push("--deep", String(Number(body.deep) || 24));
  if (body.universe === "full") args.push("--universe", "full");
  if (body.fast) args.push("--fast");

  try {
    const data = await runOpenScan(args);
    return envelope({ ok: true, command: "open-scan", data }, 200);
  } catch (e) {
    return envelope(
      {
        ok: false,
        command: "open-scan",
        error: e instanceof Error ? e.message : String(e),
      },
      502,
    );
  }
}
