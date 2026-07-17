import { spawn } from "child_process";
import crypto from "crypto";
import fs from "fs/promises";
import os from "os";
import path from "path";
import {
  analyzeEndpointUrl,
  marketRuntimeBaseUrl,
  marketRuntimeEndpointUrl,
  planEndpointUrl,
} from "./backendUrl";
import {
  analysisAgentScript,
  gammaExposureScript,
  livePlanScript,
  modelsRoot,
  optionsBookScanScript,
  optionsPickerScript,
  optionsUnusualFlowScript,
  volPackageScoreScript,
  paperLedgerScript,
  portfolioOptimizerScript,
  pythonBin,
  repoRoot,
  riskAssessmentScript,
  riskManagerScript,
  sectorMoneyFlowScript,
  sectorWatchlistScript,
  supplyChainScript,
  symbolRankerScript,
  tradeDeskScript,
  vpaScanScript,
} from "./paths";
import type { ModelMetaConfig, ModelsCatalog, ModelRankRow } from "./types";
import { normalizeLseOptionsFlow } from "./lseOptionsFlow";

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

function livePlanArgsToBody(
  args: string[],
): Record<string, string | number | boolean | undefined> {
  const body: Record<string, string | number | boolean | undefined> = {};
  for (let i = 0; i < args.length; i++) {
    const key = args[i];
    switch (key) {
      case "--symbol":
        body.symbol = args[++i];
        break;
      case "--account":
        body.account = Number(args[++i]);
        break;
      case "--peak":
        body.peak = Number(args[++i]);
        break;
      case "--history":
        body.history = args[++i];
        break;
      case "--model":
        body.model = args[++i];
        break;
      case "--symbols":
        body.symbols = args[++i];
        break;
      case "--no-model":
        body.no_model = true;
        break;
      case "--scan":
        body.scan = true;
        break;
      default:
        break;
    }
  }
  return body;
}

async function callMarketRuntimeJson(
  endpointUrl: string,
  body: Record<string, unknown>,
  label: string,
  timeoutMs: number,
): Promise<unknown> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(endpointUrl, {
      method: "POST",
      headers: marketRuntimeHeaders(true),
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!res.ok) {
      const detail = await res.text().catch(() => "");
      throw new Error(
        `${label} returned ${res.status}${detail ? `: ${detail.slice(0, 400)}` : ""}`,
      );
    }
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

function marketRuntimeHeaders(json = false): Record<string, string> {
  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  if (json) headers["Content-Type"] = "application/json";
  const token = process.env.MARKET_RUNTIME_API_TOKEN?.trim();
  if (token) headers["X-API-Key"] = token;
  return headers;
}

type MarketRuntimeDataEnvelope = {
  ok?: boolean;
  data?: unknown;
  detail?: string;
};

async function callMarketRuntimeData(
  pathName: string,
  params: Record<string, string | number | undefined>,
  label: string,
  timeoutMs: number,
): Promise<unknown> {
  const endpoint = marketRuntimeEndpointUrl(pathName);
  if (!endpoint) throw new Error("MARKET_RUNTIME_URL not set");
  const url = new URL(endpoint);
  for (const [key, value] of Object.entries(params)) {
    if (value != null && value !== "") url.searchParams.set(key, String(value));
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      headers: marketRuntimeHeaders(),
      cache: "no-store",
      signal: controller.signal,
    });
    const payload = (await res.json().catch(() => ({}))) as MarketRuntimeDataEnvelope;
    if (!res.ok || payload.ok === false) {
      throw new Error(
        `${label} returned ${res.status}${payload.detail ? `: ${payload.detail}` : ""}`,
      );
    }
    return payload.data;
  } finally {
    clearTimeout(timer);
  }
}

/** Live macro release calendar from the LSE vault. */
export async function runLseEconomicCalendar(
  params: { start: string; end: string; region?: string; limit?: number },
  timeoutMs = 12_000,
): Promise<unknown[]> {
  const data = await callMarketRuntimeData(
    "/data/reference/economic_calendar",
    {
      start: params.start,
      end: params.end,
      region: params.region ?? "US",
      order: "asc",
      limit: params.limit ?? 100,
    },
    "market-runtime economic calendar",
    timeoutMs,
  );
  return Array.isArray(data) ? data : [];
}

/** Genuine LSE options time-and-sales rows; the API key remains server-side. */
export async function runLseOptionsFlow(
  params: {
    underlying: string;
    maxDte?: number;
    minPremium?: number;
    limit?: number;
  },
  timeoutMs = 15_000,
): Promise<unknown[]> {
  const data = await callMarketRuntimeData(
    "/data/options/flow",
    {
      underlying: params.underlying,
      max_dte: params.maxDte,
      min_premium: params.minPremium,
      order: "desc",
      limit: params.limit ?? 500,
    },
    "market-runtime options flow",
    timeoutMs,
  );
  return Array.isArray(data) ? data : [];
}

async function callMarketRuntimePlan(
  args: string[],
  timeoutMs: number,
): Promise<unknown> {
  const url = planEndpointUrl();
  if (!url) {
    throw new Error("MARKET_RUNTIME_URL not set");
  }
  return callMarketRuntimeJson(
    url,
    livePlanArgsToBody(args) as Record<string, unknown>,
    "market-runtime /plan",
    timeoutMs,
  );
}

function analysisAgentArgsToBody(
  args: string[],
): Record<string, string | number | undefined> {
  const body: Record<string, string | number | undefined> = {};
  for (let i = 0; i < args.length; i++) {
    const key = args[i];
    switch (key) {
      case "--symbol":
        body.symbol = args[++i];
        break;
      case "--account":
        body.account = Number(args[++i]);
        break;
      case "--model":
        body.model = args[++i];
        break;
      case "--horizon":
        body.horizon = args[++i];
        break;
      case "--top-n":
        body.top_n = Number(args[++i]);
        break;
      default:
        break;
    }
  }
  return body;
}

async function callMarketRuntimeAnalyze(
  args: string[],
  timeoutMs: number,
): Promise<unknown> {
  const url = analyzeEndpointUrl();
  if (!url) {
    throw new Error("MARKET_RUNTIME_URL not set");
  }
  return callMarketRuntimeJson(
    url,
    analysisAgentArgsToBody(args) as Record<string, unknown>,
    "market-runtime /analyze",
    timeoutMs,
  );
}

/** Full live ticket: features + macro + v25 risk + options structure.
 *  Prefers remote market-runtime when MARKET_RUNTIME_URL is set (production).
 *  Local monorepo spawn is dev fallback only.
 */
export async function runLivePlan(
  args: string[],
  timeoutMs = 90_000,
): Promise<unknown> {
  if (marketRuntimeBaseUrl()) {
    return callMarketRuntimePlan(args, timeoutMs);
  }
  return runPythonScript(livePlanScript(), args, "live_plan", timeoutMs);
}

/** Structured Facts → Decision → Suggestion report for a single ticker.
 *  Prefers remote /analyze when MARKET_RUNTIME_URL is set.
 */
export async function runAnalysisAgent(
  args: string[],
  timeoutMs = 120_000,
): Promise<unknown> {
  if (marketRuntimeBaseUrl()) {
    return callMarketRuntimeAnalyze(args, timeoutMs);
  }
  return runPythonScript(analysisAgentScript(), args, "analysis_agent", timeoutMs);
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

/** Research-only IV–RV / surface vol package scores (never auto-trades). */
export async function runVolPackageScore(
  args: string[],
  timeoutMs = 90_000,
): Promise<unknown> {
  return runPythonScript(
    volPackageScoreScript(),
    args,
    "vol_package_score",
    timeoutMs,
  );
}

/** Gamma exposure snapshot (LSE spot + yfinance options). */
export async function runGammaExposure(
  args: string[],
  timeoutMs = 60_000,
): Promise<unknown> {
  return runPythonScript(gammaExposureScript(), args, "gamma_exposure", timeoutMs);
}

function cliValue(args: string[], flag: string): string | undefined {
  const index = args.indexOf(flag);
  return index >= 0 ? args[index + 1] : undefined;
}

/** Prefer genuine LSE time-and-sales; retain the chain proxy as local fallback. */
export async function runOptionsUnusualFlow(
  args: string[],
  timeoutMs = 90_000,
): Promise<unknown> {
  const symbol = cliValue(args, "--symbol");
  if (marketRuntimeBaseUrl() && symbol) {
    try {
      const maxDte = Number(cliValue(args, "--max-dte") ?? 45);
      const topN = Number(cliValue(args, "--top") ?? 20);
      const rows = await runLseOptionsFlow(
        {
          underlying: symbol,
          maxDte: Number.isFinite(maxDte) ? maxDte : 45,
          minPremium: 25_000,
          limit: 1000,
        },
        Math.min(timeoutMs, 20_000),
      );
      return normalizeLseOptionsFlow(rows, symbol, {
        topN: Number.isFinite(topN) ? topN : 20,
        minPremium: 25_000,
      });
    } catch (lseError) {
      try {
        const fallback = await runPythonScript(
          optionsUnusualFlowScript(),
          args,
          "options_unusual_flow",
          timeoutMs,
        );
        if (fallback && typeof fallback === "object") {
          return {
            ...(fallback as Record<string, unknown>),
            upstream_error:
              lseError instanceof Error ? lseError.message : String(lseError),
            fallback_source: "yfinance_chain_aggregate",
          };
        }
        return fallback;
      } catch (fallbackError) {
        throw new Error(
          `LSE options flow failed: ${lseError instanceof Error ? lseError.message : String(lseError)}; ` +
            `chain fallback failed: ${fallbackError instanceof Error ? fallbackError.message : String(fallbackError)}`,
        );
      }
    }
  }
  return runPythonScript(
    optionsUnusualFlowScript(),
    args,
    "options_unusual_flow",
    timeoutMs,
  );
}

/** Multi-symbol options book scan (structure + vol + flow confidence read). */
export async function runOptionsBookScan(
  args: string[],
  timeoutMs = 180_000,
): Promise<unknown> {
  return runPythonScript(
    optionsBookScanScript(),
    args,
    "options_book_scan",
    timeoutMs,
  );
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

/** Sector money-flow / rotation scanner (in/out + definitive score). */
export async function runSectorMoneyFlow(
  args: string[] = ["--source", "auto"],
  timeoutMs = 90_000,
): Promise<unknown> {
  return runPythonScript(
    sectorMoneyFlowScript(),
    args,
    "sector_money_flow",
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

let cachedCatalog: ModelsCatalog | null = null;
let cachedDirListHash = "";
let cachedWinnerStat = "";

/**
 * Dynamically discover models from filesystem + registry.
 * New models/poc_va_macdha/v* folders with signal_engine.py appear automatically.
 */
export async function loadModelsCatalog(): Promise<ModelsCatalog> {
  const root = modelsRoot();

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

  let winnerStatStr = "none";
  try {
    const winnerStat = await fs.stat(path.join(root, "WINNER.json"));
    winnerStatStr = `${winnerStat.mtimeMs}-${winnerStat.size}`;
  } catch {
    /* WINNER.json missing */
  }

  const dirListHash = versionDirs.join(",");
  if (
    cachedCatalog &&
    dirListHash === cachedDirListHash &&
    winnerStatStr === cachedWinnerStat
  ) {
    return cachedCatalog;
  }

  const winnerDoc = await readJsonSafe<{
    winner?: string;
    previous_winner?: string;
    updated_at?: string;
    selection_rule?: string;
  }>(path.join(root, "WINNER.json"));

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
      `import sys,json; sys.path.insert(0, ${JSON.stringify(tools)}); from model_registry import DEFAULT_MODEL, list_engine_models, list_desk_engines, list_featured_desk_engines, engine_kind; print(json.dumps({"default": DEFAULT_MODEL, "engines": list_engine_models(), "desk_engines": list_desk_engines(), "featured_desk_engines": list_featured_desk_engines(), "kinds": {m: engine_kind(m) for m in list_engine_models()}}))`,
    );
    const parsed = JSON.parse(reg) as {
      default: string;
      engines: string[];
      desk_engines?: string[];
      featured_desk_engines?: string[];
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
    // Surface featured research engines first in pickers (stable order).
    if (parsed.featured_desk_engines?.length) {
      const featured = parsed.featured_desk_engines.filter((id) =>
         deskEngines.includes(id),
      );
      const rest = deskEngines.filter((id) => !featured.includes(id));
      deskEngines = [...featured, ...rest];
    }
  } catch {
    /* filesystem fallback */
    deskEngines = engines.filter((id) => !id.includes("opts"));
  }

  const winner = winnerDoc?.winner ?? null;
  const featuredSet = new Set(deskEngines.slice(0, 12));
  const models = versionDirs.map((id) => {
    const kind = kindById[id] ?? (id.includes("opts") ? "options" : engines.includes(id) ? "equity" : "other");
    return {
      id,
      has_engine: engines.includes(id),
      is_default: id === defaultModel,
      is_winner: id === winner,
      kind,
      desk_compatible: deskEngines.includes(id) || kind === "equity",
      featured: featuredSet.has(id),
    };
  });

  const catalog: ModelsCatalog = {
    default_model: defaultModel,
    winner,
    previous_winner: winnerDoc?.previous_winner ?? null,
    engines,
    desk_engines: deskEngines,
    featured_desk_engines: deskEngines.filter((id) => featuredSet.has(id)),
    all_versions: versionDirs,
    models,
    updated_at: winnerDoc?.updated_at ?? null,
    selection_rule: winnerDoc?.selection_rule ?? null,
  };

  cachedCatalog = catalog;
  cachedDirListHash = dirListHash;
  cachedWinnerStat = winnerStatStr;

  return catalog;
}

export async function loadModelDetail(id: string): Promise<{
  id: string;
  has_engine: boolean;
  model_md: string | null;
  results: unknown | null;
  hypothesis: string | null;
  meta_config: ModelMetaConfig | null;
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
  const meta_config = await readJsonSafe<ModelMetaConfig>(
    path.join(dir, "meta_config.json"),
  );
  let hypothesis: string | null = null;
  try {
    hypothesis = await fs.readFile(path.join(dir, "HYPOTHESIS.md"), "utf8");
  } catch {
    hypothesis = null;
  }

  return { id, has_engine, model_md, results, hypothesis, meta_config };
}

export async function runSupplyChain(
  args: string[],
  timeoutMs = 120_000,
): Promise<unknown> {
  return runPythonScript(supplyChainScript(), args, "supply_chain", timeoutMs);
}

export type { ModelRankRow };
