import { NextResponse } from "next/server";
import { spawn } from "child_process";
import path from "path";
import fs from "fs/promises";
import { repoRoot, pythonBin } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 180;

const VALID_VARIANTS = [
  "v22_robust",
  "v22_robust_conservative",
  "v22_robust_trend_only",
  "v22_robust_vol_only",
];

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

  // Copy signal engine and hunt config
  for (const f of ["signal_engine.py", "hunt_config.json"]) {
    const src = path.join(modelDir, "code", f);
    try {
      await fs.copyFile(src, path.join(codeDir, f));
    } catch {
      throw new Error(`Missing ${f} for ${variant}`);
    }
  }

  const config = {
    source: "yfinance",
    codes,
    start_date: startDate,
    end_date: endDate,
    initial_cash: initialCash,
    commission: 0.001,
    engine: "options",
    interval: "1D",
    options_config: {
      risk_free_rate: 0.05,
      contract_multiplier: 100,
      exercise_style: "american",
    },
    strategy: {
      model_version: variant,
      note: `trade-desk robust backtest ${startDate} to ${endDate}`,
    },
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
    const variant = String(body.variant || "");
    if (!VALID_VARIANTS.includes(variant)) {
      return NextResponse.json({ ok: false, error: "Invalid variant" }, { status: 400 });
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
