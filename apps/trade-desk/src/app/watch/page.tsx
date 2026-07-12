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
import { PageHeader } from "@/components/shell/PageHeader";

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

  // API snapshot shape: { symbol, ok, data: AnalyzeResponse }
  // Analyze shape: { state, plan, model }
  const nested = asRecord(root.data);
  const payload = nested ?? root;
  const state = asRecord(payload.state) ?? asRecord(root.state) ?? payload;
  const plan = asRecord(payload.plan) ?? asRecord(root.plan);
  const symbol =
    str(state.symbol) ??
    str(payload.symbol) ??
    str(root.symbol) ??
    str(nested && asRecord(nested.state)?.symbol);
  if (!symbol) return null;

  // Skip failed snapshots without inventing fake $0 WAIT rows
  if (root.ok === false && !num(state.price) && !num(payload.price)) {
    return {
      symbol: symbol.toUpperCase(),
      action: "AVOID",
      price: 0,
      model: str(payload.model) ?? str(root.model),
      confidence: undefined,
      hitProbability: undefined,
      stop: undefined,
      rvol: undefined,
      volSurge: undefined,
      volDry: undefined,
    };
  }

  return {
    symbol: symbol.toUpperCase(),
    action:
      str(plan?.action) ??
      str(payload.action) ??
      str(root.action) ??
      str(state.action) ??
      "WAIT",
    price: num(state.price) ?? num(payload.price) ?? num(root.price) ?? 0,
    confidence:
      num(state.confidence) ?? num(payload.confidence) ?? num(root.confidence),
    hitProbability:
      num(state.hit_probability) ??
      num(state.hitProbability) ??
      num(payload.hit_probability) ??
      num(root.hit_probability) ??
      num(root.hitProbability),
    stop: num(state.stop) ?? num(payload.stop) ?? num(root.stop),
    rvol: num(state.rvol) ?? num(payload.rvol) ?? num(root.rvol),
    model:
      str(payload.model) ??
      str(state.model) ??
      str(root.model) ??
      str(asRecord(payload.model_selection)?.model),
    volSurge:
      bool(state.vol_surge) ?? bool(payload.vol_surge) ?? bool(root.vol_surge),
    volDry: bool(state.vol_dry) ?? bool(payload.vol_dry) ?? bool(root.vol_dry),
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
    symbols: "NVDA, MU, APLD",
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
  const [scanning, setScanning] = useState(false);
  const [scanNote, setScanNote] = useState<string | null>(null);

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

  const runMarketScan = useCallback(async () => {
    setScanning(true);
    setError(null);
    setScanNote("Scanning market (VPA → WINNER deep)… 1–3 min");
    try {
      const res = await fetch("/api/open-scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: controls.model || "auto",
          top: 12,
          deep: 20,
          universe: "open",
        }),
      });
      const json: unknown = await res.json().catch(() => null);
      const env = asRecord(json);
      if (!res.ok || (env && env.ok === false)) {
        throw new Error(str(env?.error) ?? `Open scan failed (${res.status})`);
      }
      const data = asRecord(env?.data) ?? env;
      const watchlist = Array.isArray(data?.watchlist)
        ? (data!.watchlist as unknown[]).map(String).filter(Boolean)
        : [];
      const plays = Array.isArray(data?.top_plays)
        ? (data!.top_plays as unknown[])
        : [];
      if (watchlist.length) {
        setControls((c) => ({ ...c, symbols: watchlist.slice(0, 18).join(", ") }));
      }
      const nPlays = plays.length;
      const hot = Array.isArray(data?.hot_sectors)
        ? (data!.hot_sectors as unknown[]).map(String).join(", ")
        : "";
      setScanNote(
        `Scan done · ${nPlays} plays · watchlist ${watchlist.length}` +
          (hot ? ` · hot: ${hot}` : "") +
          " · press Start",
      );
      // Auto-start board on the new list
      setRunning(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Market scan failed");
      setScanNote(null);
    } finally {
      setScanning(false);
    }
  }, [controls.model]);

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
    <div className="td-page">
      <PageHeader
        title="Watch"
        description={`Live board for the open · Market scan finds plays across hot sectors + liquid names (WINNER model). Poll every ${Math.max(15, controls.every)}s.`}
      />

      <WatchControls
        value={controls}
        models={models}
        running={running}
        loading={loading && running}
        scanning={scanning}
        onChange={setControls}
        onStart={() => setRunning(true)}
        onStop={() => setRunning(false)}
        onMarketScan={() => void runMarketScan()}
      />

      {scanNote ? (
        <p className="text-[12px] px-1" style={{ color: "var(--td-ink-300)" }}>
          {scanNote}
        </p>
      ) : null}

      <div className="td-panel overflow-hidden">
        <WatchBoard
          rows={rows}
          alerts={alerts}
          lastTick={lastTick}
          loading={loading}
          error={error}
        />
      </div>
    </div>
  );
}
