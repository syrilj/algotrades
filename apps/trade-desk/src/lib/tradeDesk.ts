import { spawn } from "child_process";
import crypto from "crypto";
import fs from "fs/promises";
import os from "os";
import path from "path";
import {
  livePlanScript,
  modelsRoot,
  optionsPickerScript,
  paperLedgerScript,
  portfolioOptimizerScript,
  pythonBin,
  repoRoot,
  riskAssessmentScript,
  riskManagerScript,
  sectorWatchlistScript,
  symbolRankerScript,
  tradeDeskScript,
  vpaScanScript,
} from "./paths";
import type { ModelsCatalog, ModelRankRow } from "./types";

const DEFAULT_TIMEOUT_MS = 120_000;

function extractJson(stdout: string): unknown {
  const trimmed = stdout.trim();
  const startArr = trimmed.indexOf("[");
  const startObj = trimmed.indexOf("{");
  let start = -1;
  if (startArr === -1) start = startObj;
  else if (startObj === -1) start = startArr;
  else start = Math.min(startArr, startObj);
  if (start === -1) {
    throw new Error("No JSON in trade_desk stdout");
  }
  return JSON.parse(trimmed.slice(start));
}

function runPythonScript(
  script: string,
  args: string[],
  label: string,
  timeoutMs = DEFAULT_TIMEOUT_MS,
  forceJsonFlag = true,
): Promise<unknown> {
  const py = pythonBin();
  const cwd = repoRoot();
  const fullArgs = forceJsonFlag ? [...args, "--json"] : args;

  return new Promise((resolve, reject) => {
    const child = spawn(py, [script, ...fullArgs], {
      cwd,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: "1",
        PYTHONPATH: [cwd, path.join(cwd, "tools"), path.join(cwd, "services")]
          .concat(process.env.PYTHONPATH ? [process.env.PYTHONPATH] : [])
          .join(path.delimiter),
      },
    });
    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      reject(new Error(`${label} timed out after ${timeoutMs}ms`));
    }, timeoutMs);

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
            `${label} exited ${code}: ${stderr.slice(-800) || stdout.slice(-400)}`,
          ),
        );
        return;
      }
      try {
        resolve(extractJson(stdout));
      } catch (e) {
        reject(
          new Error(
            `JSON parse failed: ${(e as Error).message}. stderr: ${stderr.slice(-400)}`,
          ),
        );
      }
    });
  });
}

export async function runTradeDesk(
  args: string[],
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<unknown> {
  return runPythonScript(tradeDeskScript(), args, "trade_desk", timeoutMs);
}

/** Full live ticket: features + macro + v25 risk + options structure. */
export async function runLivePlan(
  args: string[],
  timeoutMs = 90_000,
): Promise<unknown> {
  return runPythonScript(livePlanScript(), args, "live_plan", timeoutMs);
}

export async function runSymbolRanker(
  args: string[],
  timeoutMs = 30_000,
): Promise<unknown> {
  return runPythonScript(symbolRankerScript(), args, "symbol_ranker", timeoutMs);
}

export async function runPaperLedger(
  args: string[],
  timeoutMs = 30_000,
): Promise<unknown> {
  return runPythonScript(paperLedgerScript(), args, "paper_ledger", timeoutMs);
}

/** Direct options structure pick (bull call spread / long call). */
export async function runOptionsPicker(
  args: string[],
  timeoutMs = 60_000,
): Promise<unknown> {
  return runPythonScript(optionsPickerScript(), args, "options_picker", timeoutMs);
}

export async function runRiskManager(
  args: string[],
  timeoutMs = 30_000,
): Promise<unknown> {
  return runPythonScript(riskManagerScript(), args, "risk_manager", timeoutMs);
}

/** Research-backed risk assessment (Kelly, VaR/ES, drawdown, Sharpe/Sortino/Calmar). */
export async function runRiskAssessment(
  input: Record<string, unknown>,
  timeoutMs = 30_000,
): Promise<unknown> {
  const tmp = path.join(os.tmpdir(), `risk-assessment-${crypto.randomUUID()}.json`);
  await fs.writeFile(tmp, JSON.stringify(input), "utf8");
  try {
    const raw = await runPythonScript(
      riskAssessmentScript(),
      ["assess", "--json-file", tmp],
      "risk_assessment",
      timeoutMs,
    );
    const envelope = raw as { ok?: boolean; data?: unknown; error?: string };
    if (envelope?.ok === false) {
      throw new Error(envelope.error || "risk assessment failed");
    }
    return envelope?.data ?? envelope;
  } finally {
    await fs.unlink(tmp).catch(() => {});
  }
}

/** Research VPA+VWAP scan (CALL/PUT bias + DNA peg tags). Not 80% WR live. */
export async function runVpaScan(
  args: string[],
  timeoutMs = 180_000,
): Promise<unknown> {
  return runPythonScript(vpaScanScript(), args, "vpa_scan", timeoutMs);
}

/** Sector RS vs SPY weekly watchlist (research). */
export async function runSectorWatchlist(
  args: string[] = [],
  timeoutMs = 90_000,
): Promise<unknown> {
  return runPythonScript(
    sectorWatchlistScript(),
    args,
    "sector_watchlist",
    timeoutMs,
  );
}

/** Portfolio optimiser (MPT, efficient frontier, risk parity, factor tilt). */
export async function runPortfolioOptimizer(
  input: Record<string, unknown>,
  timeoutMs = 30_000,
): Promise<unknown> {
  const tmp = path.join(os.tmpdir(), `portfolio-${crypto.randomUUID()}.json`);
  await fs.writeFile(tmp, JSON.stringify(input), "utf8");
  try {
    const raw = await runPythonScript(
      portfolioOptimizerScript(),
      ["--input", tmp],
      "portfolio_optimizer",
      timeoutMs,
    );
    const envelope = raw as { ok?: boolean; data?: unknown; error?: string };
    if (envelope?.ok === false) {
      throw new Error(envelope.error || "portfolio optimizer failed");
    }
    return envelope?.data ?? envelope;
  } finally {
    await fs.unlink(tmp).catch(() => {});
  }
}

async function readJsonSafe<T>(file: string): Promise<T | null> {
  try {
    const raw = await fs.readFile(file, "utf8");
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

function runPythonSnippet(code: string, timeoutMs = 15_000): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn(pythonBin(), ["-c", code], { cwd: repoRoot() });
    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      reject(new Error("python snippet timeout"));
    }, timeoutMs);
    child.stdout.on("data", (d: Buffer) => {
      stdout += d.toString();
    });
    child.stderr.on("data", (d: Buffer) => {
      stderr += d.toString();
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (code !== 0) reject(new Error(stderr || `exit ${code}`));
      else resolve(stdout.trim());
    });
  });
}

/**
 * Dynamically discover models from filesystem + registry.
 * New models/poc_va_macdha/v* folders with signal_engine.py appear automatically.
 */
export async function loadModelsCatalog(): Promise<ModelsCatalog> {
  const root = modelsRoot();
  const winnerDoc = await readJsonSafe<{
    winner?: string;
    previous_winner?: string;
    updated_at?: string;
    selection_rule?: string;
  }>(path.join(root, "WINNER.json"));

  let entries: string[] = [];
  try {
    entries = await fs.readdir(root);
  } catch {
    entries = [];
  }

  const versionDirs = (
    await Promise.all(
      entries
        .filter((name) => name.startsWith("v"))
        .map(async (name) => {
          const full = path.join(root, name);
          try {
            const st = await fs.stat(full);
            return st.isDirectory() ? name : null;
          } catch {
            return null;
          }
        }),
    )
  )
    .filter((x): x is string => Boolean(x))
    .sort();

  const engines: string[] = [];
  for (const id of versionDirs) {
    try {
      await fs.access(path.join(root, id, "signal_engine.py"));
      engines.push(id);
    } catch {
      /* no engine */
    }
  }

  let defaultModel = "v15_meta_xgb";
  let deskEngines: string[] = [];
  const kindById: Record<string, "equity" | "options" | "other"> = {};
  try {
    const tools = path.join(repoRoot(), "tools");
    const reg = await runPythonSnippet(
      `import sys,json; sys.path.insert(0, ${JSON.stringify(tools)}); from model_registry import DEFAULT_MODEL, list_engine_models, list_desk_engines, engine_kind; print(json.dumps({"default": DEFAULT_MODEL, "engines": list_engine_models(), "desk_engines": list_desk_engines(), "kinds": {m: engine_kind(m) for m in list_engine_models()}}))`,
    );
    const parsed = JSON.parse(reg) as {
      default: string;
      engines: string[];
      desk_engines?: string[];
      kinds?: Record<string, "equity" | "options" | "other">;
    };
    defaultModel = parsed.default || defaultModel;
    if (parsed.engines?.length) {
      const set = new Set([...parsed.engines, ...engines]);
      engines.length = 0;
      engines.push(...[...set].sort());
    }
    deskEngines = (parsed.desk_engines ?? engines.filter((id) => !id.includes("opts"))).slice().sort();
    if (parsed.kinds) Object.assign(kindById, parsed.kinds);
  } catch {
    /* filesystem fallback */
    deskEngines = engines.filter((id) => !id.includes("opts"));
  }

  const winner = winnerDoc?.winner ?? null;
  const models = versionDirs.map((id) => {
    const kind = kindById[id] ?? (id.includes("opts") ? "options" : engines.includes(id) ? "equity" : "other");
    return {
      id,
      has_engine: engines.includes(id),
      is_default: id === defaultModel,
      is_winner: id === winner,
      kind,
      desk_compatible: deskEngines.includes(id) || kind === "equity",
    };
  });

  return {
    default_model: defaultModel,
    winner,
    previous_winner: winnerDoc?.previous_winner ?? null,
    engines,
    desk_engines: deskEngines,
    all_versions: versionDirs,
    models,
    updated_at: winnerDoc?.updated_at ?? null,
    selection_rule: winnerDoc?.selection_rule ?? null,
  };
}

export async function loadModelDetail(id: string): Promise<{
  id: string;
  has_engine: boolean;
  model_md: string | null;
  results: unknown | null;
  hypothesis: string | null;
}> {
  const root = modelsRoot();
  const dir = path.join(root, id);
  let has_engine = false;
  try {
    await fs.access(path.join(dir, "signal_engine.py"));
    has_engine = true;
  } catch {
    has_engine = false;
  }

  let model_md: string | null = null;
  try {
    model_md = await fs.readFile(path.join(dir, "MODEL.md"), "utf8");
  } catch {
    try {
      model_md = await fs.readFile(path.join(dir, "HYPOTHESIS.md"), "utf8");
    } catch {
      model_md = null;
    }
  }

  const results = await readJsonSafe(path.join(dir, "results.json"));
  let hypothesis: string | null = null;
  try {
    hypothesis = await fs.readFile(path.join(dir, "HYPOTHESIS.md"), "utf8");
  } catch {
    hypothesis = null;
  }

  return { id, has_engine, model_md, results, hypothesis };
}

export type { ModelRankRow };
