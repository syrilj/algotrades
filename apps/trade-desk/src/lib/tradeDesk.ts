import { spawn } from "child_process";
import fs from "fs/promises";
import path from "path";
import { modelsRoot, pythonBin, repoRoot, tradeDeskScript } from "./paths";
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

export async function runTradeDesk(
  args: string[],
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<unknown> {
  const py = pythonBin();
  const script = tradeDeskScript();
  const cwd = repoRoot();

  return new Promise((resolve, reject) => {
    const child = spawn(py, [script, ...args, "--json"], {
      cwd,
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    });
    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      reject(new Error(`trade_desk timed out after ${timeoutMs}ms`));
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
            `trade_desk exited ${code}: ${stderr.slice(-800) || stdout.slice(-400)}`,
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
 * New models/poc_va_macdha/v*_*/signal_engine.py appear automatically.
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
  try {
    const tools = path.join(repoRoot(), "tools");
    const reg = await runPythonSnippet(
      `import sys,json; sys.path.insert(0, ${JSON.stringify(tools)}); from model_registry import DEFAULT_MODEL, list_engine_models; print(json.dumps({"default": DEFAULT_MODEL, "engines": list_engine_models()}))`,
    );
    const parsed = JSON.parse(reg) as { default: string; engines: string[] };
    defaultModel = parsed.default || defaultModel;
    if (parsed.engines?.length) {
      const set = new Set([...parsed.engines, ...engines]);
      engines.length = 0;
      engines.push(...[...set].sort());
    }
  } catch {
    /* filesystem fallback */
  }

  const winner = winnerDoc?.winner ?? null;
  const models = versionDirs.map((id) => ({
    id,
    has_engine: engines.includes(id),
    is_default: id === defaultModel,
    is_winner: id === winner,
  }));

  return {
    default_model: defaultModel,
    winner,
    previous_winner: winnerDoc?.previous_winner ?? null,
    engines,
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
