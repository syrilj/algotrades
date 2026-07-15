import { NextResponse } from "next/server";
import { spawn } from "child_process";
import path from "path";
import fs from "fs/promises";
import { repoRoot, pythonBin } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 180;

function sanitizeSymbol(sym: string): string {
  return sym.trim().toUpperCase().replace(/[^A-Z0-9]/g, "");
}

function isValidDate(d: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(d) && !isNaN(Date.parse(d));
}

async function runBacktest(variant: string, codes: string[], startDate: string, endDate: string, initialCash: number) {
  const root = repoRoot();
  const modelDir = path.join(root, "models", "poc_va_macdha", variant);
  const runDir = path.join(root, "runs", "trade_desk_robust", `${variant}_${startDate}_${endDate}`);
  const codeDir = path.join(runDir, "code");
  await fs.mkdir(codeDir, { recursive: true });

  // Copy signal engine and hunt config, checking code/ first, falling back to model root
  for (const f of ["signal_engine.py", "hunt_config.json"]) {
    let src = path.join(modelDir, "code", f);
    try {
      await fs.access(src);
    } catch {
      src = path.join(modelDir, f);
    }

    try {
      await fs.copyFile(src, path.join(codeDir, f));
    } catch {
      if (f === "signal_engine.py") {
        throw new Error(`Missing mandatory signal_engine.py for ${variant}`);
      }
    }
  }

  // Load model's native config.json if present to merge details
  let nativeConfigPath = path.join(modelDir, "code", "config.json");
  try {
    await fs.access(nativeConfigPath);
  } catch {
    nativeConfigPath = path.join(modelDir, "config.json");
  }

  let nativeConfig: {
    source?: string;
    commission?: number;
    engine?: string;
    interval?: string;
    strategy?: Record<string, unknown>;
    options_config?: Record<string, unknown>;
  } = {};
  try {
    const raw = await fs.readFile(nativeConfigPath, "utf-8");
    nativeConfig = JSON.parse(raw);
  } catch {
    // optional
  }

  const config = {
    source: nativeConfig.source || "yfinance",
    codes,
    start_date: startDate,
    end_date: endDate,
    initial_cash: initialCash,
    commission: nativeConfig.commission ?? 0.001,
    engine: nativeConfig.engine || "options",
    interval: nativeConfig.interval || "1D",
    strategy: {
      model_version: variant,
      note: `trade-desk robust backtest ${startDate} to ${endDate}`,
      ...(nativeConfig.strategy || {}),
    },
    ...((nativeConfig.engine || "options") === "options" ? {
      options_config: {
        risk_free_rate: 0.05,
        contract_multiplier: 100,
        exercise_style: "american",
        ...(nativeConfig.options_config || {}),
      }
    } : {}),
  };
  await fs.writeFile(path.join(runDir, "config.json"), JSON.stringify(config, null, 2));

  return new Promise<{ ok: boolean; metrics: unknown; error?: string }>((resolve, reject) => {
    const child = spawn(pythonBin(), [
      "-c",
      `from pathlib import Path; from backtest.runner import main; main(Path("${runDir}").resolve())`,
    ], { cwd: root });

    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      reject(new Error("Backtest timed out"));
    }, 160_000);

    child.stdout.on("data", (d: Buffer) => { stdout += d.toString(); });
    child.stderr.on("data", (d: Buffer) => { stderr += d.toString(); });
    child.on("error", (err) => { clearTimeout(timer); reject(err); });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (code !== 0) {
        resolve({ ok: false, metrics: null, error: stderr.slice(-800) || `exit ${code}` });
        return;
      }
      try {
        const start = stdout.lastIndexOf("{");
        const metrics = JSON.parse(stdout.slice(start));
        resolve({ ok: true, metrics });
      } catch {
        resolve({ ok: false, metrics: null, error: `parse failed: ${stderr.slice(-400)}` });
      }
    });
  });
}

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const variant = String(body.variant || "").trim();
    if (!variant || variant.includes("..") || variant.includes("/") || variant.includes("\\")) {
      return NextResponse.json({ ok: false, error: "Invalid variant format" }, { status: 400 });
    }

    const root = repoRoot();
    const modelDir = path.join(root, "models", "poc_va_macdha", variant);
    try {
      const stats = await fs.stat(modelDir);
      if (!stats.isDirectory()) {
        throw new Error("Not a directory");
      }
    } catch {
      return NextResponse.json({ ok: false, error: `Model variant '${variant}' not found` }, { status: 404 });
    }

    const symbols = Array.isArray(body.symbols) ? body.symbols : [];
    const codes = symbols
      .map((s: unknown) => sanitizeSymbol(String(s)))
      .filter(Boolean)
      .map((s: string) => `${s}.US`);
    if (!codes.length || codes.length > 8) {
      return NextResponse.json({ ok: false, error: "1-8 symbols required" }, { status: 400 });
    }

    const startDate = String(body.startDate || "");
    const endDate = String(body.endDate || "");
    if (!isValidDate(startDate) || !isValidDate(endDate)) {
      return NextResponse.json({ ok: false, error: "Invalid dates (YYYY-MM-DD)" }, { status: 400 });
    }

    const initialCash = Number(body.initialCash ?? 1000000);
    if (!Number.isFinite(initialCash) || initialCash < 1000) {
      return NextResponse.json({ ok: false, error: "Invalid initial cash" }, { status: 400 });
    }

    const result = await runBacktest(variant, codes, startDate, endDate, initialCash);
    return NextResponse.json(result, { status: result.ok ? 200 : 502 });
  } catch (e) {
    return NextResponse.json({ ok: false, error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}
