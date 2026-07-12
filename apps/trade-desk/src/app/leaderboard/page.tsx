"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ApiEnvelope, ModelRankRow, ModelsCatalog } from "@/lib/types";
import {
  LeaderboardControls,
  type LeaderboardMode,
} from "@/components/leaderboard/LeaderboardControls";
import { LeaderboardTable } from "@/components/leaderboard/LeaderboardTable";
import {
  ModelSidePanel,
  type LeaderboardRow,
} from "@/components/leaderboard/ModelSidePanel";

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const body = (await res.json()) as ApiEnvelope<T> | T;
  if (body && typeof body === "object" && "ok" in body) {
    const env = body as ApiEnvelope<T>;
    if (!env.ok) throw new Error(env.error || "Request failed");
    return env.data as T;
  }
  return body as T;
}

export default function LeaderboardPage() {
  const [mode, setMode] = useState<LeaderboardMode>("portfolio");
  const [symbol, setSymbol] = useState("IONQ");
  const [enginesOnly, setEnginesOnly] = useState(false);
  const [rows, setRows] = useState<LeaderboardRow[]>([]);
  const [selected, setSelected] = useState<LeaderboardRow | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadLeaderboard = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      let winner: string | null = null;
      let defaultModel = "";
      try {
        const catalog = await fetchJson<ModelsCatalog>("/api/models");
        winner = catalog.winner;
        defaultModel = catalog.default_model;
      } catch {
        /* badges optional if catalog unavailable */
      }

      const params = new URLSearchParams();
      if (enginesOnly) params.set("enginesOnly", "1");
      if (mode === "symbol" && symbol.trim()) {
        params.set("symbol", symbol.trim().toUpperCase());
      }
      const qs = params.toString();
      const data = await fetchJson<ModelRankRow[]>(
        `/api/leaderboard${qs ? `?${qs}` : ""}`,
      );
      const list = Array.isArray(data) ? data : [];
      const enriched: LeaderboardRow[] = list.map((r) => ({
        ...r,
        isWinner: Boolean(winner && r.model === winner),
        isDefault: Boolean(defaultModel && r.model === defaultModel),
      }));
      setRows(enriched);
      setSelected((prev) => {
        if (!prev) return enriched[0] ?? null;
        return enriched.find((r) => r.model === prev.model) ?? enriched[0] ?? null;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load leaderboard");
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [enginesOnly, mode, symbol]);

  useEffect(() => {
    void loadLeaderboard();
  }, [loadLeaderboard]);

  const maxScore = useMemo(
    () => Math.max(1, ...rows.map((r) => r.score || 0)),
    [rows],
  );

  return (
    <main
      className="min-h-screen px-4 py-6 sm:px-6"
      style={{
        background: "var(--td-ink-950, #0B1014)",
        color: "var(--td-ink-100, #E2E8F0)",
        fontFamily: "var(--td-font-body, IBM Plex Sans, ui-sans-serif, system-ui, sans-serif)",
      }}
    >
      <header className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[20px] font-medium leading-tight">Model Leaderboard</h1>
          <p
            className="text-[13px] mt-1"
            style={{ color: "var(--td-ink-400, #64748B)" }}
          >
            Portfolio and per-symbol ranks from live registry — not a hardcoded list.
          </p>
        </div>
        <LeaderboardControls
          mode={mode}
          symbol={symbol}
          enginesOnly={enginesOnly}
          onModeChange={setMode}
          onSymbolChange={setSymbol}
          onEnginesOnlyChange={setEnginesOnly}
          onRefresh={() => void loadLeaderboard()}
          loading={loading}
        />
      </header>

      {error ? (
        <p
          className="mb-4 text-[13px]"
          style={{ color: "var(--td-action-avoid, #A34848)" }}
          role="alert"
        >
          {error}
        </p>
      ) : null}

      <div
        className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_280px] gap-0 rounded-sm overflow-hidden"
        style={{ border: "1px solid var(--td-ink-700, #243040)" }}
      >
        <div
          className="min-w-0"
          style={{ background: "var(--td-ink-900, #12181F)" }}
        >
          {loading && !rows.length ? (
            <div
              className="p-8 text-[13px]"
              style={{ color: "var(--td-ink-400, #64748B)" }}
            >
              Loading ranks…
            </div>
          ) : (
            <LeaderboardTable
              rows={rows}
              selectedModel={selected?.model}
              onSelect={setSelected}
            />
          )}
        </div>
        <ModelSidePanel
          row={selected}
          maxScore={maxScore}
          onClose={() => setSelected(null)}
        />
      </div>
    </main>
  );
}
