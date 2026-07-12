import fs from "fs/promises";
import path from "path";

import { repoRoot } from "@/lib/paths";

export type EvolveClaimLevel =
  | "THIN"
  | "RESEARCH"
  | "CLAIM"
  | "BLOCKED_DATA"
  | "ERROR"
  | string;

export type EvolveRow = {
  id: string;
  mode?: string;
  tag?: string;
  claim_level?: EvolveClaimLevel;
  data_track?: string;
  ret?: number;
  sharpe?: number;
  dd?: number;
  n?: number;
  wr?: number;
  utility?: number;
  may_auto_promote?: boolean;
  pass_bar?: { passed?: boolean; reasons?: string[] };
  from_cache?: boolean;
  reused?: boolean;
  error?: string;
  multi_lock?: string;
};

export type EvolveFinalize = {
  action?: string;
  top_evolve?: string;
  top_utility?: number;
  top_claim?: string;
  frozen_equity_winner?: string;
  frozen_options_winner?: string;
  reasons?: string[];
  ts?: string;
};

export type EvolveRunSummary = {
  id: string;
  path: string;
  mtime: number;
  phase?: string;
  track?: string;
  cash?: number;
  updated_at?: string;
  promote?: string[];
  ranking: EvolveRow[];
  multi_lock?: Record<string, { status?: string; ok?: boolean; flags?: string[] }>;
  finalize?: EvolveFinalize | null;
  generations?: Array<{
    gen?: number;
    best_id?: string;
    best_utility?: number;
    n_mutations?: number;
  }>;
  leaderboard_md?: string | null;
};

function runsDir(): string {
  return path.join(repoRoot(), "runs");
}

async function exists(p: string): Promise<boolean> {
  try {
    await fs.access(p);
    return true;
  } catch {
    return false;
  }
}

async function readJson<T>(p: string): Promise<T | null> {
  try {
    const raw = await fs.readFile(p, "utf8");
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

function attachMultiLock(
  ranking: EvolveRow[],
  multi?: Record<string, { status?: string; ok?: boolean; flags?: string[] }>,
): EvolveRow[] {
  if (!multi) return ranking;
  return ranking.map((r) => ({
    ...r,
    multi_lock: multi[r.id]?.status,
  }));
}

export async function listEvolveRunIds(): Promise<
  Array<{ id: string; mtime: number; hasState: boolean }>
> {
  const root = runsDir();
  let entries: string[] = [];
  try {
    entries = await fs.readdir(root);
  } catch {
    return [];
  }
  const out: Array<{ id: string; mtime: number; hasState: boolean }> = [];
  for (const name of entries) {
    if (!name.startsWith("evolve_")) continue;
    if (name === "evolve_cache" || name === "evolve_latest" || name.endsWith(".log")) {
      continue;
    }
    const dir = path.join(root, name);
    try {
      const st = await fs.stat(dir);
      if (!st.isDirectory()) continue;
      const hasState = await exists(path.join(dir, "STATE.json"));
      out.push({ id: name, mtime: st.mtimeMs, hasState });
    } catch {
      /* skip */
    }
  }
  out.sort((a, b) => b.mtime - a.mtime);
  return out;
}

export async function resolveLatestEvolveId(): Promise<string | null> {
  const root = runsDir();
  const latestLink = path.join(root, "evolve_latest");
  try {
    const target = await fs.readlink(latestLink);
    const base = path.basename(target);
    if (await exists(path.join(root, base, "STATE.json"))) return base;
  } catch {
    /* not a symlink or missing */
  }
  // Prefer known good full ranks
  for (const preferred of [
    "evolve_equity_1h",
    "evolve_full_equity",
    "evolve_full_options",
    "evolve_smoke_rank",
  ]) {
    if (await exists(path.join(root, preferred, "STATE.json"))) return preferred;
  }
  const listed = await listEvolveRunIds();
  const withState = listed.find((x) => x.hasState);
  return withState?.id ?? null;
}

export async function loadEvolveRun(runId: string): Promise<EvolveRunSummary | null> {
  const root = runsDir();
  const dir = path.join(root, runId);
  if (!(await exists(dir))) return null;

  const state = await readJson<Record<string, unknown>>(path.join(dir, "STATE.json"));
  if (!state) return null;

  let mtime = 0;
  try {
    mtime = (await fs.stat(dir)).mtimeMs;
  } catch {
    mtime = Date.now();
  }

  const rankingRaw = (state.ranking || state.screen || []) as Array<
    EvolveRow & { model?: string }
  >;
  const multi = state.multi_lock as EvolveRunSummary["multi_lock"];
  const normalized: EvolveRow[] = rankingRaw
    .map((r) => ({
      ...r,
      id: r.id || r.model || "",
    }))
    .filter((r) => Boolean(r.id));
  const ranking = attachMultiLock(normalized, multi);

  const finalize =
    (await readJson<EvolveFinalize>(path.join(dir, "FINALIZE.json"))) || null;

  let leaderboard_md: string | null = null;
  try {
    leaderboard_md = await fs.readFile(path.join(dir, "LEADERBOARD.md"), "utf8");
  } catch {
    leaderboard_md = null;
  }

  return {
    id: runId,
    path: path.relative(repoRoot(), dir),
    mtime,
    phase: typeof state.phase === "string" ? state.phase : undefined,
    track: typeof state.track === "string" ? state.track : undefined,
    cash: typeof state.cash === "number" ? state.cash : undefined,
    updated_at:
      typeof state.updated_at === "string" ? state.updated_at : undefined,
    promote: Array.isArray(state.promote)
      ? (state.promote as string[])
      : ranking.filter((r) => r.may_auto_promote).map((r) => r.id),
    ranking,
    multi_lock: multi,
    finalize,
    generations: Array.isArray(state.generations)
      ? (state.generations as EvolveRunSummary["generations"])
      : undefined,
    leaderboard_md,
  };
}

export async function loadWinners(): Promise<{
  equity: string | null;
  options: string | null;
}> {
  const models = path.join(repoRoot(), "models", "poc_va_macdha");
  const eq = await readJson<{ winner?: string }>(path.join(models, "WINNER.json"));
  const op = await readJson<{ winner?: string }>(
    path.join(models, "OPTIONS_WINNER.json"),
  );
  return {
    equity: eq?.winner ?? null,
    options: op?.winner ?? null,
  };
}

export type EvolveBrain = {
  epoch?: number;
  accepted?: number;
  rejected?: number;
  best_utility_oos?: number;
  best_utility_train?: number;
  lessons?: string[];
  history?: Array<Record<string, unknown>>;
  best_genome?: Record<string, unknown>;
  genome?: Record<string, unknown>;
  updated_at?: string;
  meta_recipe?: Record<string, unknown> | null;
};

export type AuditFinding = {
  code: string;
  severity: string;
  title: string;
  detail: string;
  evidence?: Record<string, unknown>;
};

export type AuditReport = {
  target: string;
  verdict: string;
  score: number;
  findings: AuditFinding[];
  metrics_snapshot?: Record<string, unknown>;
  ts?: string;
  may_promote?: boolean;
  blocks_train_accept?: boolean;
};

export async function loadBrain(): Promise<EvolveBrain | null> {
  const p = path.join(runsDir(), "evolve_brain", "BRAIN.json");
  return readJson<EvolveBrain>(p);
}

export async function loadLatestAudits(): Promise<AuditReport[]> {
  const dir = path.join(runsDir(), "evolve_audits");
  try {
    const files = (await fs.readdir(dir)).filter(
      (f) => f.startsWith("LATEST_") && f.endsWith(".json"),
    );
    const out: AuditReport[] = [];
    for (const f of files) {
      const r = await readJson<AuditReport>(path.join(dir, f));
      if (r) out.push(r);
    }
    out.sort((a, b) => (a.score ?? 0) - (b.score ?? 0));
    return out;
  } catch {
    return [];
  }
}

export async function loadEvolveBoard(runId?: string | null): Promise<{
  run: EvolveRunSummary | null;
  runs: Array<{ id: string; mtime: number; hasState: boolean }>;
  winners: { equity: string | null; options: string | null };
  summary_path: string | null;
  brain: EvolveBrain | null;
  audits: AuditReport[];
}> {
  const runs = await listEvolveRunIds();
  const id = runId || (await resolveLatestEvolveId());
  const run = id ? await loadEvolveRun(id) : null;
  const winners = await loadWinners();
  const summary = path.join(runsDir(), "EVOLVE_RESULTS_SUMMARY.md");
  const brain = await loadBrain();
  const audits = await loadLatestAudits();
  return {
    run,
    runs: runs.slice(0, 24),
    winners,
    summary_path: (await exists(summary))
      ? path.relative(repoRoot(), summary)
      : null,
    brain,
    audits,
  };
}
