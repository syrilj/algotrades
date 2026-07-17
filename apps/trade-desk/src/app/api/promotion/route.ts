import { spawn } from "child_process";
import { createHash, timingSafeEqual } from "crypto";
import { NextResponse } from "next/server";
import { pythonBin, repoRoot } from "@/lib/paths";
import type { ApiEnvelope } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ADMIN_TOKEN_ENV = "PROMOTION_ADMIN_TOKEN";

/** Constant-work comparison over SHA-256 digests, including length mismatch. */
function secureTokenMatches(configured: string | undefined, provided: string | null): boolean {
  const configuredDigest = createHash("sha256").update(configured ?? "", "utf8").digest();
  const providedDigest = createHash("sha256").update(provided ?? "", "utf8").digest();
  const equal = timingSafeEqual(configuredDigest, providedDigest);
  return Boolean(configured) && Boolean(provided) && equal;
}

function requestAdminToken(req: Request): string | null {
  const authorization = req.headers.get("authorization");
  if (authorization?.startsWith("Bearer ")) return authorization.slice(7);
  return req.headers.get("x-admin-token");
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

function runCLI(args: string[]): Promise<unknown> {
  const bin = pythonBin();
  const root = repoRoot();

  return new Promise((resolve, reject) => {
    const child = spawn(bin, ["tools/evolve/promotion_queue.py", ...args], {
      cwd: root,
      env: process.env,
    });
    let stdout = "";
    let stderr = "";

    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      reject(new Error("CLI command timed out"));
    }, 60_000);

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
        reject(new Error(stderr.trim() || `CLI exited with code ${code}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout));
      } catch (e) {
        reject(new Error(`Failed to parse CLI output: ${(e as Error).message}. raw: ${stdout}`));
      }
    });
  });
}

export async function GET() {
  try {
    const data = await runCLI(["list"]);
    return envelope({ ok: true, command: "promotion-list", data }, 200);
  } catch (e) {
    return envelope(
      {
        ok: false,
        command: "promotion-list",
        error: e instanceof Error ? e.message : String(e),
      },
      502,
    );
  }
}

export async function POST(req: Request) {
  if (!secureTokenMatches(process.env[ADMIN_TOKEN_ENV], requestAdminToken(req))) {
    return envelope(
      {
        ok: false,
        command: "promotion-action",
        error: process.env[ADMIN_TOKEN_ENV]
          ? "Unauthorized"
          : `${ADMIN_TOKEN_ENV} is not configured; promotion is disabled`,
      },
      process.env[ADMIN_TOKEN_ENV] ? 401 : 503,
    );
  }

  let body: { action?: string; id?: string; reason?: string };
  try {
    body = await req.json();
  } catch {
    return envelope({ ok: false, command: "promotion-action", error: "Invalid JSON" }, 400);
  }

  const { action, id, reason } = body;
  if (!id || !/^[a-zA-Z0-9_\-\.]+$/.test(id)) {
    return envelope({ ok: false, command: "promotion-action", error: "Invalid or missing ID" }, 400);
  }

  if (action !== "approve" && action !== "reject") {
    return envelope({ ok: false, command: "promotion-action", error: "action must be approve or reject" }, 400);
  }

  const args: string[] = [action, id];
  if (action === "reject" && reason) {
    args.push("--reason", reason);
  }

  try {
    const data = await runCLI(args);
    return envelope({ ok: true, command: "promotion-action", data }, 200);
  } catch (e) {
    return envelope(
      {
        ok: false,
        command: "promotion-action",
        error: e instanceof Error ? e.message : String(e),
      },
      502,
    );
  }
}
