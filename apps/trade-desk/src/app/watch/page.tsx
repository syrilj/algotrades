"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  WatchBoard,
  type WatchBoardRow,
} from "@/components/watch/WatchBoard";
import {
  WatchControls,
  type WatchControlsValue,
} from "@/components/watch/WatchControls";
import type { ApiEnvelope, ModelsCatalog } from "@/lib/types";

function parseSymbols(raw: string): string[] {
  return raw
    .split(/[,\s]+/)
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean)
    .slice(0, 18);
}

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === "object" ? (v as Record<string, unknown>) : null;
}

function num(v: unknown): number | undefined {
  return typeof v === "number" && Number.isFinite(v) ? v : undefined;
}

function str(v: unknown): string | undefined {
  return typeof v === "string" ? v : undefined;
}

function bool(v: unknown): boolean | undefined {
  return typeof v === "boolean" ? v : undefined;
}

function normalizeWatchRow(item: unknown): WatchBoardRow | null {
  const root = asRecord(item);
  if (!root) return null;

  const state = asRecord(root.state) ?? root;
  const plan = asRecord(root.plan);
  const symbol = str(state.symbol) ?? str(root.symbol);
  if (!symbol) return null;

  return {
    symbol: symbol.toUpperCase(),
    action:
      str(plan?.action) ?? str(root.action) ?? str(state.action) ?? "WAIT",
    price: num(state.price) ?? num(root.price) ?? 0,
    confidence: num(state.confidence) ?? num(root.confidence),
    hitProbability:
      num(state.hit_probability) ??
      num(state.hitProbability) ??
      num(root.hit_probability) ??
      num(root.hitProbability),
    stop: num(state.stop) ?? num(root.stop),
    rvol: num(state.rvol) ?? num(root.rvol),
    model: str(root.model) ?? str(state.model),
    volSurge: bool(state.vol_surge) ?? bool(root.vol_surge),
    volDry: bool(state.vol_dry) ?? bool(root.vol_dry),
  };
}

function extractWatchRows(payload: unknown): WatchBoardRow[] {
  const env = asRecord(payload);
  const data: unknown = env?.data ?? payload;

  if (Array.isArray(data)) {
    return data.map(normalizeWatchRow).filter(Boolean) as WatchBoardRow[];
  }

  const rec = asRecord(data);
  if (!rec) return [];

  for (const c of [rec.rows, rec.snapshots, rec.results, rec.items]) {
    if (Array.isArray(c)) {
      return c.map(normalizeWatchRow).filter(Boolean) as WatchBoardRow[];
    }
  }

  const single = normalizeWatchRow(data);
  return single ? [single] : [];
}

function diffAlerts(prev: WatchBoardRow[], next: WatchBoardRow[]): string[] {
  const map = new Map(prev.map((r) => [r.symbol, r.action]));
  const out: string[] = [];
  for (const row of next) {
    const before = map.get(row.symbol);
    if (before && before !== row.action) {
      out.push(`${row.symbol} ${before} → ${row.action}`);
    }
  }
  return out;
}

async function fetchModels(): Promise<string[]> {
  const res = await fetch("/api/models");
  const json = (await res.json()) as ApiEnvelope<ModelsCatalog> | ModelsCatalog;
  const catalog =
    "data" in json && json.data ? json.data : (json as ModelsCatalog);
  const ids =
    catalog.models?.map((m) => m.id) ??
    catalog.all_versions ??
    catalog.engines ??
    [];
  return [...new Set(ids)].filter(Boolean);
}

export default function WatchPage() {
  const [controls, setControls] = useState<WatchControlsValue>({
    symbols: "NVDA, MU, ANET",
    every: 30,
    interval: "1m",
    model: "auto",
  });
  const [models, setModels] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [loading, setLoading] = useState(false);
  const [rows, setRows] = useState<WatchBoardRow[]>([]);
  const [alerts, setAlerts] = useState<string[]>([]);
  const [lastTick, setLastTick] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const controlsRef = useRef(controls);
  const rowsRef = useRef(rows);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    controlsRef.current = controls;
  }, [controls]);

  useEffect(() => {
    rowsRef.current = rows;
  }, [rows]);

  useEffect(() => {
    let cancelled = false;
    fetchModels()
      .then((ids) => {
        if (!cancelled) setModels(ids);
      })
      .catch(() => {
        if (!cancelled) setModels([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const tick = useCallback(async () => {
    const cfg = controlsRef.current;
    const symbols = parseSymbols(cfg.symbols);
    if (!symbols.length) {
      setError("Add at least one symbol");
      setRunning(false);
      return;
    }

    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    setLoading(true);
    setError(null);

    try {
      const body: Record<string, unknown> = {
        symbols,
        interval: cfg.interval,
      };
      if (cfg.model && cfg.model !== "auto") body.model = cfg.model;

      const res = await fetch("/api/watch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: ac.signal,
      });

      const json: unknown = await res.json().catch(() => null);
      const env = asRecord(json);
      if (!res.ok || (env && env.ok === false)) {
        throw new Error(
          str(env?.error) ?? `Watch request failed (${res.status})`,
        );
      }

      const next = extractWatchRows(json);
      const changed = diffAlerts(rowsRef.current, next);
      setRows(next);
      if (changed.length) setAlerts(changed);
      setLastTick(str(env?.asof) ?? new Date().toISOString());
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      setError(err instanceof Error ? err.message : "Watch request failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!running) {
      abortRef.current?.abort();
      return;
    }

    void tick();
    const everyMs = Math.max(15, controls.every) * 1000;
    const id = window.setInterval(() => {
      void tick();
    }, everyMs);

    return () => {
      window.clearInterval(id);
      abortRef.current?.abort();
    };
  }, [running, controls.every, tick]);

  return (
    <div className="flex min-h-full flex-col bg-[var(--td-ink-900,#12181F)] text-[var(--td-ink-200,#CBD5E1)]">
      <header className="border-b border-[var(--td-ink-600,#334155)] px-4 py-3">
        <h1 className="text-[20px] font-semibold text-[var(--td-ink-100,#E2E8F0)]">
          Watch
        </h1>
        <p className="text-[12px] text-[var(--td-ink-400,#64748B)]">
          Multi-symbol board · poll every {Math.max(15, controls.every)}s
        </p>
      </header>

      <WatchControls
        value={controls}
        models={models}
        running={running}
        loading={loading && running}
        onChange={setControls}
        onStart={() => setRunning(true)}
        onStop={() => setRunning(false)}
      />

      <WatchBoard
        rows={rows}
        alerts={alerts}
        lastTick={lastTick}
        loading={loading}
        error={error}
      />
    </div>
  );
}
