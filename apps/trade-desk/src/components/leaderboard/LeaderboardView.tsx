"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
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
import { PageHeader } from "@/components/shell/PageHeader";

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

export function LeaderboardView({ showHeader = true }: { showHeader?: boolean }) {
  const searchParams = useSearchParams();
  const qSymbol = searchParams.get("symbol")?.toUpperCase() ?? "";

  const [mode, setMode] = useState<LeaderboardMode>(qSymbol ? "symbol" : "portfolio");
  const [symbol, setSymbol] = useState(qSymbol || "IONQ");
  const [enginesOnly, setEnginesOnly] = useState(false);
  const [rows, setRows] = useState<LeaderboardRow[]>([]);
  const [selected, setSelected] = useState<LeaderboardRow | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!qSymbol) return;
    setSymbol(qSymbol);
    setMode("symbol");
  }, [qSymbol]);

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
    <div className="flex flex-col gap-4">
      {showHeader ? (
        <PageHeader
          title="Model leaderboard"
          description="Portfolio and per-symbol ranks from the live registry — not a hardcoded list."
          actions={
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
          }
        />
      ) : null}

      {error ? (
        <p className="td-alert td-alert--error" role="alert">
          {error}
        </p>
      ) : null}

      <div
        className="td-panel grid grid-cols-1 overflow-hidden lg:grid-cols-[minmax(0,1fr)_280px]"
      >
        <div className="min-w-0">
          {loading && !rows.length ? (
            <div className="p-8 text-[13px]" style={{ color: "var(--td-ink-400)" }}>
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
    </div>
  );
}
