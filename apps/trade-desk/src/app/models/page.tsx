"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import type { ApiEnvelope, EngineModelInfo, ModelsCatalog } from "@/lib/types";
import { ModelBadges } from "@/components/leaderboard/ModelBadges";

async function fetchCatalog(): Promise<ModelsCatalog> {
  const res = await fetch("/api/models", { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const body = (await res.json()) as ApiEnvelope<ModelsCatalog> | ModelsCatalog;
  if (body && typeof body === "object" && "ok" in body) {
    const env = body as ApiEnvelope<ModelsCatalog>;
    if (!env.ok || !env.data) throw new Error(env.error || "Failed to load models");
    return env.data;
  }
  return body as ModelsCatalog;
}

function buildModelsList(catalog: ModelsCatalog): EngineModelInfo[] {
  if (catalog.models?.length) return catalog.models;

  const engineSet = new Set(catalog.engines ?? []);
  const versions = catalog.all_versions?.length
    ? catalog.all_versions
    : [...engineSet];
  const ids = [...new Set([...versions, ...engineSet])].sort();

  return ids.map((id) => ({
    id,
    has_engine: engineSet.has(id),
    is_default: id === catalog.default_model,
    is_winner: Boolean(catalog.winner && id === catalog.winner),
  }));
}

export default function ModelsCatalogPage() {
  const [catalog, setCatalog] = useState<ModelsCatalog | null>(null);
  const [models, setModels] = useState<EngineModelInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"grid" | "list">("grid");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchCatalog();
      setCatalog(data);
      setModels(buildModelsList(data));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load catalog");
      setModels([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

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
          <h1 className="text-[20px] font-medium leading-tight">Models</h1>
          <p
            className="text-[13px] mt-1"
            style={{ color: "var(--td-ink-400, #64748B)" }}
          >
            All discovered versions (engines + non-engines). Refresh after adding a new{" "}
            <code className="text-[12px]">v*</code> folder.
          </p>
          {catalog ? (
            <p
              className="text-[12px] mt-1 tabular-nums"
              style={{
                color: "var(--td-ink-400, #64748B)",
                fontFamily: "var(--td-font-mono, ui-monospace, Menlo, monospace)",
              }}
            >
              {models.length} models · default {catalog.default_model}
              {catalog.winner ? ` · winner ${catalog.winner}` : ""}
              {catalog.updated_at ? ` · updated ${catalog.updated_at}` : ""}
            </p>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          <div
            className="inline-flex rounded-sm overflow-hidden"
            style={{ border: "1px solid var(--td-ink-600, #334155)" }}
            role="group"
            aria-label="View mode"
          >
            {(["grid", "list"] as const).map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => setView(v)}
                className="px-3 py-1.5 text-[13px] capitalize"
                style={{
                  background:
                    view === v
                      ? "var(--td-brand, #2F6F7A)"
                      : "var(--td-ink-800, #1A222C)",
                  color:
                    view === v
                      ? "var(--td-ink-100, #E2E8F0)"
                      : "var(--td-ink-300, #94A3B8)",
                }}
                aria-pressed={view === v}
              >
                {v}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={loading}
            className="h-8 px-3 text-[13px] rounded-sm disabled:opacity-50"
            style={{
              background: "var(--td-ink-800, #1A222C)",
              border: "1px solid var(--td-ink-600, #334155)",
              color: "var(--td-ink-200, #CBD5E1)",
            }}
          >
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
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

      {loading && !models.length ? (
        <p className="text-[13px]" style={{ color: "var(--td-ink-400, #64748B)" }}>
          Discovering models from API…
        </p>
      ) : null}

      {!loading && !models.length && !error ? (
        <p className="text-[13px]" style={{ color: "var(--td-ink-400, #64748B)" }}>
          No models discovered yet.
        </p>
      ) : null}

      {view === "grid" ? (
        <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 list-none p-0 m-0">
          {models.map((m) => (
            <li key={m.id}>
              <Link
                href={`/models/${encodeURIComponent(m.id)}`}
                className="block p-4 rounded-sm h-full transition-colors"
                style={{
                  background: "var(--td-ink-900, #12181F)",
                  border: "1px solid var(--td-ink-700, #243040)",
                  boxShadow: m.is_winner
                    ? "inset 2px 0 0 var(--td-brand, #2F6F7A)"
                    : undefined,
                }}
              >
                <p
                  className="text-[14px] font-medium mb-2"
                  style={{
                    fontFamily:
                      "var(--td-font-mono, ui-monospace, Menlo, monospace)",
                  }}
                >
                  {m.id}
                </p>
                <ModelBadges
                  isWinner={m.is_winner}
                  isDefault={m.is_default}
                  hasEngine={m.has_engine}
                />
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <ul
          className="list-none p-0 m-0 rounded-sm overflow-hidden"
          style={{ border: "1px solid var(--td-ink-700, #243040)" }}
        >
          {models.map((m) => (
            <li
              key={m.id}
              style={{
                borderBottom: "1px solid var(--td-ink-800, #1A222C)",
                background: "var(--td-ink-900, #12181F)",
                boxShadow: m.is_winner
                  ? "inset 2px 0 0 var(--td-brand, #2F6F7A)"
                  : undefined,
              }}
            >
              <Link
                href={`/models/${encodeURIComponent(m.id)}`}
                className="flex flex-wrap items-center justify-between gap-2 px-4 py-3"
              >
                <span
                  className="text-[13px]"
                  style={{
                    fontFamily:
                      "var(--td-font-mono, ui-monospace, Menlo, monospace)",
                    color: "var(--td-ink-100, #E2E8F0)",
                  }}
                >
                  {m.id}
                </span>
                <ModelBadges
                  isWinner={m.is_winner}
                  isDefault={m.is_default}
                  hasEngine={m.has_engine}
                />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
