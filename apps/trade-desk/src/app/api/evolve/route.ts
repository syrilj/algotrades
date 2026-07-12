import { spawn } from "child_process";
import fs from "fs/promises";
import path from "path";
import { NextResponse } from "next/server";

import { loadEvolveBoard } from "@/lib/evolve";
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

/** GET — load evolve STATE / leaderboard from runs (default: latest). */
export async function GET(req: Request) {
  const url = new URL(req.url);
  const runId = url.searchParams.get("run") || undefined;

  try {
    const data = await loadEvolveBoard(runId);
    return envelope(
      {
        ok: true,
        command: "evolve",
        data,
      },
      200,
    );
  } catch (e) {
    return envelope(
      {
        ok: false,
        command: "evolve",
        error: e instanceof Error ? e.message : String(e),
      },
      502,
    );
  }
}

type PostBody = {
  action?: "rank" | "train" | "brain" | "audit";
  track?: "equity" | "options";
  quick?: boolean;
  models?: string;
  cash?: number;
  epochs?: number;
  base?: string;
};

/**
 * POST — kick a rank job (quick by default). Long full ranks: run CLI offline.
 * Returns the new run board when finished.
 */
export async function POST(req: Request) {
  let body: PostBody = {};
  try {
    body = (await req.json()) as PostBody;
  } catch {
    body = {};
  }

  const action = body.action || "rank";
  if (
    action !== "rank" &&
    action !== "train" &&
    action !== "brain" &&
    action !== "audit"
  ) {
    return envelope(
      {
        ok: false,
        command: "evolve",
        error: "action must be rank | train | brain | audit",
      },
      400,
    );
  }

  const track = body.track === "options" ? "options" : "equity";
  const cash = Number(body.cash) > 0 ? Number(body.cash) : track === "options" ? 1000 : 10000;
  const root = repoRoot();
  const bin = pythonBin();

  if (action === "brain" || action === "audit") {
    try {
      const data = await loadEvolveBoard(undefined);
      const brainPath = path.join(root, "runs", "evolve_brain", "BRAIN.json");
      let brain: unknown = null;
      try {
        brain = JSON.parse(await fs.readFile(brainPath, "utf8"));
      } catch {
        brain = null;
      }

      if (action === "brain") {
        return envelope(
          { ok: true, command: "evolve-brain", data: { ...data, brain } },
          200,
        );
      }

      const models =
        body.models?.trim() ||
        "v23_devin_overlay,v20b_macro_light,v15_meta_xgb,v35_softstruct_bag8";

      const audits = await new Promise<unknown[]>((resolve, reject) => {
        const child = spawn(
          bin,
          ["tools/evolve_pipeline.py", "audit", "--models", models, "--json"],
          { cwd: root, env: process.env },
        );
        let stdout = "";
        let stderr = "";
        const timer = setTimeout(() => {
          child.kill("SIGTERM");
          reject(new Error("Audit timed out"));
        }, 120_000);
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
        child.on("close", () => {
          clearTimeout(timer);
          try {
            const start = stdout.indexOf("[");
            if (start < 0) {
              reject(
                new Error(
                  stderr.split("\n").filter(Boolean).slice(-5).join(" ") ||
                    "audit produced no JSON",
                ),
              );
              return;
            }
            resolve(JSON.parse(stdout.slice(start)) as unknown[]);
          } catch (e) {
            reject(
              e instanceof Error
                ? e
                : new Error(stderr || "audit parse failed"),
            );
          }
        });
      });

      return envelope(
        {
          ok: true,
          command: "evolve-audit",
          data: { ...data, brain, audits },
        },
        200,
      );
    } catch (e) {
      return envelope(
        {
          ok: false,
          command: action === "audit" ? "evolve-audit" : "evolve-brain",
          error: e instanceof Error ? e.message : String(e),
        },
        502,
      );
    }
  }

  const tag =
    action === "train"
      ? `evolve_train_ui_${Date.now()}`
      : `evolve_ui_${track}_${Date.now()}`;
  const outRel = `runs/${tag}`;

  let args: string[];
  if (action === "train") {
    const epochs = Math.min(20, Math.max(1, Number(body.epochs) || 3));
    args = [
      "tools/evolve_pipeline.py",
      "train",
      "--track",
      track,
      "--cash",
      String(cash),
      "--epochs",
      String(epochs),
      "--out",
      outRel,
      "--meta-every",
      "0",
    ];
    if (body.base?.trim()) args.push("--base", body.base.trim());
    else if (track === "equity") args.push("--base", "v23_devin_overlay");
    else args.push("--base", "v35_softstruct_bag8");
  } else {
    const quick = body.quick !== false;
    args = [
      "tools/evolve_pipeline.py",
      "rank",
      "--track",
      track,
      "--cash",
      String(cash),
      "--out",
      outRel,
      "--no-multi-lock",
    ];
    if (quick) args.push("--quick");
    if (body.models?.trim()) {
      args.push("--models", body.models.trim());
    } else if (track === "equity") {
      args.push(
        "--models",
        "v23_devin_overlay,v20b_macro_light,v15_meta_xgb,v16_meta_risk",
      );
    } else {
      args.push("--elite");
    }
  }

  try {
    await new Promise<void>((resolve, reject) => {
      const child = spawn(bin, args, { cwd: root, env: process.env });
      let stderr = "";
      const timer = setTimeout(() => {
        child.kill("SIGTERM");
        reject(
          new Error(
            action === "train"
              ? "Train timed out — use CLI: tools/evolve_pipeline.py train --epochs 20"
              : "Evolve rank timed out (use CLI for full multi-lock)",
          ),
        );
      }, 280_000);

      child.stderr.on("data", (d: Buffer) => {
        stderr += d.toString();
      });
      child.stdout.on("data", () => {
        /* drain */
      });
      child.on("error", (err) => {
        clearTimeout(timer);
        reject(err);
      });
      child.on("close", (code) => {
        clearTimeout(timer);
        if (code === 0) resolve();
        else
          reject(
            new Error(
              stderr.split("\n").filter(Boolean).slice(-8).join(" ") ||
                `exit ${code}`,
            ),
          );
      });
    });

    const data = await loadEvolveBoard(tag);
    let brain: unknown = null;
    if (action === "train") {
      try {
        brain = JSON.parse(
          await fs.readFile(
            path.join(root, "runs", "evolve_brain", "BRAIN.json"),
            "utf8",
          ),
        );
      } catch {
        brain = null;
      }
    }
    return envelope(
      {
        ok: true,
        command: action === "train" ? "evolve-train" : "evolve-rank",
        data: { ...data, ran: tag, brain },
      },
      200,
    );
  } catch (e) {
    return envelope(
      {
        ok: false,
        command: action === "train" ? "evolve-train" : "evolve-rank",
        error: e instanceof Error ? e.message : String(e),
      },
      502,
    );
  }
}
