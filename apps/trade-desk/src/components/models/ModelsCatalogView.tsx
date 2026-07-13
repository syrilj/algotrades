"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import type { ApiEnvelope, EngineModelInfo, ModelsCatalog } from "@/lib/types";
import { ModelBadges } from "@/components/leaderboard/ModelBadges";
import { PageHeader } from "@/components/shell/PageHeader";
import { analyzeHref, modelHref } from "@/lib/routes";

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

export function ModelsCatalogView({ showHeader = true }: { showHeader?: boolean }) {
  const searchParams = useSearchParams();
  const qSymbol = searchParams.get("symbol")?.toUpperCase() ?? "";

  const [catalog, setCatalog] = useState<ModelsCatalog | null>(null);
  const [models, setModels] = useState<EngineModelInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"grid" | "list">("grid");
  const [testSymbol, setTestSymbol] = useState(qSymbol);

  useEffect(() => {
    setTestSymbol(qSymbol);
  }, [qSymbol]);

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

  const meta = catalog ? (
    <span className="tabular" style={{ fontFamily: "var(--td-font-mono)" }}>
      {models.length} models · default {catalog.default_model}
      {catalog.winner ? ` · winner ${catalog.winner}` : ""}
      {catalog.updated_at ? ` · updated ${catalog.updated_at}` : ""}
    </span>
  ) : null;

  const controls = (
    <div className="flex flex-wrap items-center gap-3">
      {meta}
      <label className="flex items-center gap-2 text-[13px]" style={{ color: "var(--td-ink-300)" }}>
        <span className="text-[12px]" style={{ color: "var(--td-ink-400)" }}>
          Test symbol
        </span>
        <input
          value={testSymbol}
          onChange={(e) => setTestSymbol(e.target.value.toUpperCase())}
          placeholder="APLD"
          className="td-input w-24"
          style={{ fontFamily: "var(--td-font-mono)" }}
          aria-label="Test symbol"
        />
      </label>
      <div
        className="inline-flex overflow-hidden rounded-[var(--td-radius-sm)]"
        style={{ border: "1px solid var(--td-hairline)" }}
        role="group"
        aria-label="View mode"
      >
        {(["grid", "list"] as const).map((v) => {
          const active = view === v;
          return (
            <button
              key={v}
              type="button"
              onClick={() => setView(v)}
              className="px-3 py-1.5 text-[13px] capitalize"
              style={{
                background: active ? "var(--td-canvas)" : "var(--td-surface-card)",
                color: active ? "var(--td-ink)" : "var(--td-body)",
              }}
              aria-pressed={active}
            >
              {v}
            </button>
          );
        })}
      </div>
      <button
        type="button"
        onClick={() => void refresh()}
        disabled={loading}
        className="td-btn td-btn-ghost"
      >
        {loading ? "Refreshing…" : "Refresh"}
      </button>
    </div>
  );

  return (
    <>
      {showHeader ? (
        <PageHeader
          title="Models"
          description={
            <>
              All discovered versions (engines + non-engines). Refresh after adding a new{" "}
              <code className="text-[12px]">v*</code> folder.
            </>
          }
          actions={controls}
        />
      ) : (
        controls
      )}

      {error ? (
        <p className="td-alert td-alert--error" role="alert">
          {error}
        </p>
      ) : null}

      {loading && !models.length ? (
        <p className="td-muted">Discovering models from API…</p>
      ) : null}

      {!loading && !models.length && !error ? (
        <p className="td-muted">No models discovered yet.</p>
      ) : null}

      {view === "grid" ? (
        <ul className="m-0 grid list-none grid-cols-1 gap-3 p-0 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {models.map((m) => {
            const detailHref = testSymbol
              ? `${modelHref(m.id)}?symbol=${encodeURIComponent(testSymbol)}`
              : modelHref(m.id);
            const testHref = analyzeHref({ symbol: testSymbol, model: m.id });
            return (
              <li key={m.id}>
                <div
                  className="td-panel flex h-full flex-col justify-between p-4"
                  style={{
                    boxShadow: m.is_winner ? "inset 2px 0 0 var(--td-brand)" : undefined,
                  }}
                >
                  <div>
                    <div className="mb-2 flex items-start justify-between gap-2">
                      <Link
                        href={detailHref}
                        className="text-[14px] font-medium no-underline"
                        style={{ fontFamily: "var(--td-font-mono)" }}
                      >
                        {m.id}
                      </Link>
                      <Link
                        href={testHref}
                        className="text-[10px] font-semibold uppercase tracking-wide no-underline"
                        style={{ color: "var(--td-brand)" }}
                      >
                        Test
                      </Link>
                    </div>
                    <ModelBadges
                      isWinner={m.is_winner}
                      isDefault={m.is_default}
                      hasEngine={m.has_engine}
                    />
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      ) : (
        <ul className="td-panel m-0 list-none overflow-hidden p-0">
          {models.map((m) => {
            const detailHref = testSymbol
              ? `${modelHref(m.id)}?symbol=${encodeURIComponent(testSymbol)}`
              : modelHref(m.id);
            const testHref = analyzeHref({ symbol: testSymbol, model: m.id });
            return (
              <li
                key={m.id}
                style={{
                  borderBottom: "1px solid var(--td-ink-800)",
                  boxShadow: m.is_winner ? "inset 2px 0 0 var(--td-brand)" : undefined,
                }}
              >
                <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
                  <Link
                    href={detailHref}
                    className="text-[13px] no-underline"
                    style={{
                      fontFamily: "var(--td-font-mono)",
                      color: "var(--td-ink-100)",
                    }}
                  >
                    {m.id}
                  </Link>
                  <div className="flex items-center gap-2">
                    <ModelBadges
                      isWinner={m.is_winner}
                      isDefault={m.is_default}
                      hasEngine={m.has_engine}
                    />
                    <Link
                      href={testHref}
                      className="text-[10px] font-semibold uppercase tracking-wide no-underline"
                      style={{ color: "var(--td-brand)" }}
                    >
                      Test
                    </Link>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
