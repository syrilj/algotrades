"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
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
import { liveHref } from "@/lib/routes";

function parseSymbols(raw: string): string[] {
  return raw
    .split(/[,\s]+/)
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean)
    .slice(0, 24);
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

function strList(v: unknown): string[] | undefined {
  if (!Array.isArray(v)) return undefined;
  const out = v.map(String).filter(Boolean);
  return out.length ? out : undefined;
}

function normalizeWatchRow(item: unknown): WatchBoardRow | null {
  const root = asRecord(item);
  if (!root) return null;

  // API snapshot shape: { symbol, ok, data: AnalyzeResponse }
  // Analyze shape: { state, plan, model, size }
  // Open-scan play shape: flat { symbol, action, do_next, ... }
  const nested = asRecord(root.data);
  const payload = nested ?? root;
  const state = asRecord(payload.state) ?? asRecord(root.state) ?? payload;
  const plan = asRecord(payload.plan) ?? asRecord(root.plan);
  const size = asRecord(payload.size) ?? asRecord(payload.sizing) ?? asRecord(root.size);
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
      doNext: str(root.error) ? `Scan/analyze failed: ${str(root.error)}` : "Analyze failed",
    };
  }

  const breakoutLevel =
    num(state.breakout_level) ??
    num(payload.breakout_level) ??
    num(root.breakout_level);
  const entry =
    num(state.entry) ?? num(payload.entry) ?? num(root.entry);
  const price =
    num(state.price) ?? num(payload.price) ?? num(root.price) ?? 0;

  const action =
    str(plan?.action) ??
    str(payload.action) ??
    str(root.action) ??
    str(state.action) ??
    "WAIT";

  return {
    symbol: symbol.toUpperCase(),
    action,
    price,
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
    entry,
    breakoutLevel,
    trigger: breakoutLevel ?? entry,
    trailArm:
      num(state.trail_arm) ?? num(payload.trail_arm) ?? num(root.trail_arm),
    riskPerShare:
      num(state.risk_per_share) ??
      num(payload.risk_per_share) ??
      num(root.risk_per_share),
    setupKind:
      str(state.setup_kind) ?? str(payload.setup_kind) ?? str(root.setup_kind),
    why: str(plan?.why) ?? str(payload.why) ?? str(root.why),
    doNext:
      str(plan?.do_next) ??
      str(payload.do_next) ??
      str(root.do_next) ??
      str(plan?.confidence_note),
    missing:
      strList(state.missing) ??
      strList(payload.missing) ??
      strList(root.missing),
    shares: num(size?.shares) ?? num(payload.shares) ?? num(root.shares),
    dollarRisk:
      num(size?.dollar_risk) ??
      num(payload.dollar_risk) ??
      num(root.dollar_risk),
    score: num(payload.score) ?? num(root.score),
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

  for (const c of [rec.rows, rec.snapshots, rec.results, rec.items, rec.top_plays, rec.all_deep]) {
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
  // Prefer desk-routable engines (featured research first from API order)
  const desk = catalog.desk_engines ?? [];
  const eng = catalog.engines ?? [];
  const ids = desk.length
    ? [...desk, ...eng.filter((id) => !desk.includes(id))]
    : catalog.models?.map((m) => m.id) ?? catalog.all_versions ?? eng;
  return [...new Set(ids)].filter(Boolean);
}

export function WatchDesk({ showHeader = true }: { showHeader?: boolean }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const qSymbol = searchParams.get("symbol")?.trim().toUpperCase() ?? "";
  const accountRaw = Number(searchParams.get("account") || "1000");
  const account = Number.isFinite(accountRaw) && accountRaw > 0 ? accountRaw : 1000;
  const [controls, setControls] = useState<WatchControlsValue>({
    symbols: qSymbol || "NVDA, MU, APLD",
    every: 30,
    interval: "1m",
    model: "auto",
    universe: "open",
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

  // Seed from last open scan if present (fast paint with do_next already filled)
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/open-scan");
        if (!res.ok) return;
        const json: unknown = await res.json();
        const env = asRecord(json);
        const data = asRecord(env?.data) ?? env;
        if (!data || cancelled) return;
        const plays = extractWatchRows({ data });
        if (plays.length && rowsRef.current.length === 0) {
          setRows(plays);
          setLastTick(str(data.asof) ?? null);
          const wl = Array.isArray(data.watchlist)
            ? (data.watchlist as unknown[]).map(String).filter(Boolean)
            : plays.map((p) => p.symbol);
          if (wl.length) {
            setControls((c) => ({
              ...c,
              symbols: wl.slice(0, 18).join(", "),
            }));
          }
          const hot = Array.isArray(data.hot_sectors)
            ? (data.hot_sectors as unknown[]).map(String).join(", ")
            : "";
          setScanNote(
            `Cached scan · ${plays.length} rows · scanned ${num(data.scanned) ?? "—"}` +
              (hot ? ` · hot: ${hot}` : "") +
              " · Start to live-poll, or Market scan to refresh",
          );
        }
      } catch {
        /* ignore cold cache */
      }
    })();
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
        account,
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
  }, [account]);

  const runMarketScan = useCallback(async () => {
    setScanning(true);
    setError(null);
    const wide = controls.universe === "full";
    setScanNote(
      wide
        ? "Wide scan (full universe + day movers)… 2–5 min"
        : "Scanning market (hot sectors + core + movers)… 1–3 min",
    );
    try {
      const res = await fetch("/api/open-scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: controls.model || "auto",
          top: 16,
          deep: wide ? 36 : 28,
          universe: wide ? "full" : "open",
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
      // Seed board immediately from ranked plays (do_next / math already present)
      const playRows = extractWatchRows({ data });
      if (playRows.length) {
        setRows(playRows);
        setLastTick(str(data?.asof) ?? new Date().toISOString());
      }
      if (watchlist.length) {
        setControls((c) => ({
          ...c,
          symbols: watchlist.slice(0, 18).join(", "),
        }));
      }
      const nPlays = playRows.filter((r) =>
        /BUY|BREAKOUT WATCH|PULLBACK/i.test(r.action),
      ).length;
      const hot = Array.isArray(data?.hot_sectors)
        ? (data!.hot_sectors as unknown[]).map(String).join(", ")
        : "";
      const movers = Array.isArray(data?.day_movers)
        ? (data!.day_movers as unknown[]).map(String).slice(0, 8).join(", ")
        : "";
      setScanNote(
        `Scan done · ${nPlays} actionable · watchlist ${watchlist.length}` +
          (hot ? ` · hot: ${hot}` : "") +
          (movers ? ` · movers: ${movers}` : "") +
          ` · scanned ${num(data?.scanned) ?? "—"}` +
          " · live-polling",
      );
      // Live-poll refreshes levels/confidence on the new list
      setRunning(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Market scan failed");
      setScanNote(null);
    } finally {
      setScanning(false);
    }
  }, [controls.model, controls.universe]);

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

  const body = (
    <>
      {showHeader ? (
        <PageHeader
          title="Watch"
          description={`Operator board · action + trigger + what you're waiting on · conf/hit math. Market scan ranks plays across sectors + day movers. Poll every ${Math.max(15, controls.every)}s.`}
        />
      ) : null}

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
        <div
          className="td-alert"
          style={{
            border: "1px solid var(--td-hairline)",
            background: "var(--td-surface-soft)",
            color: "var(--td-ink-300)",
          }}
        >
          {scanNote}
        </div>
      ) : null}

      <div className="td-panel overflow-hidden">
        <WatchBoard
          rows={rows}
          alerts={alerts}
          lastTick={lastTick}
          loading={loading}
          error={error}
          onSelectSymbol={(sym) => {
            router.push(liveHref(sym, "ticket", account));
          }}
        />
      </div>
    </>
  );

  return showHeader ? <div className="td-page">{body}</div> : body;
}
