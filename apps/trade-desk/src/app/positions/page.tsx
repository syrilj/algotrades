"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { PortfolioDesk } from "@/components/portfolio/PortfolioDesk";
import { PositionsTable } from "@/components/positions/PositionsTable";
import { HubTabs } from "@/components/shell/HubTabs";
import { PageHeader } from "@/components/shell/PageHeader";
import {
  hubPanelId,
  positionsHubTabs,
  resolvePositionsView,
  type PositionsView,
} from "@/lib/routes";
import type { ApiEnvelope, PositionsResponse } from "@/lib/types";

function PositionsDesk() {
  const searchParams = useSearchParams();
  const view: PositionsView = resolvePositionsView(searchParams.get("view"));
  const [data, setData] = useState<PositionsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [closingId, setClosingId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/positions?status=all&mark=1");
      const json = (await res.json()) as ApiEnvelope<PositionsResponse>;
      if (!res.ok || json.ok === false || !json.data) {
        throw new Error(json.error ?? `Positions failed (${res.status})`);
      }
      setData(json.data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Positions failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (view === "portfolio") return;
    void refresh();
  }, [refresh, view]);

  const handleClose = useCallback(
    async (id: string, exit: number) => {
      setClosingId(id);
      setError(null);
      try {
        const res = await fetch("/api/positions", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "close", id, exit }),
        });
        const json = (await res.json()) as ApiEnvelope<{ position: unknown }>;
        if (!res.ok || json.ok === false) {
          throw new Error(json.error ?? `Close failed (${res.status})`);
        }
        await refresh();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Close failed");
      } finally {
        setClosingId(null);
      }
    },
    [refresh],
  );

  const handleUpdate = useCallback(
    async (id: string, updates: { shares?: number; entry?: number; stop?: number }) => {
      setError(null);
      try {
        const res = await fetch("/api/positions", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "update", id, ...updates }),
        });
        const json = (await res.json()) as ApiEnvelope<{ position: unknown }>;
        if (!res.ok || json.ok === false) {
          throw new Error(json.error ?? `Update failed (${res.status})`);
        }
        await refresh();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Update failed");
      }
    },
    [refresh],
  );

  const handleDelete = useCallback(
    async (id: string) => {
      setError(null);
      try {
        const res = await fetch("/api/positions", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "delete", id }),
        });
        const json = (await res.json()) as ApiEnvelope<{ success: boolean }>;
        if (!res.ok || json.ok === false) {
          throw new Error(json.error ?? `Delete failed (${res.status})`);
        }
        await refresh();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Delete failed");
      }
    },
    [refresh],
  );


  const baseTabs = positionsHubTabs();
  const openCount =
    data?.positions.filter((p) => p.status === "open").length ?? 0;
  const closedCount =
    data?.positions.filter((p) => p.status === "closed").length ?? 0;
  const tabs = baseTabs.map((tab) => {
    if (tab.key === "open" && openCount > 0) {
      return { ...tab, badge: openCount };
    }
    if (tab.key === "history" && closedCount > 0) {
      return { ...tab, badge: closedCount };
    }
    return tab;
  });
  const activeLabel = tabs.find((t) => t.key === view)?.label ?? "Open Positions";

  return (
    <div className="td-page">
      <PageHeader
        eyebrow="Desk"
        title="Portfolio"
        description="Paper ledger, marks, and weight scenarios — open risk, closed outcomes, and construction metrics on your basket."
        meta={
          data?.asof && view !== "portfolio" ? (
            <span className="tabular" style={{ fontFamily: "var(--td-font-mono)" }}>
              asof {data.asof.slice(0, 19).replace("T", " ")}Z
              {data.marked ? " · marks refreshed" : null}
              {openCount > 0 ? ` · ${openCount} open` : null}
            </span>
          ) : (
            <span className="td-chip">open · portfolio · history</span>
          )
        }
        actions={
          <HubTabs tabs={tabs} active={view} aria-label="Portfolio views" />
        }
      />

      <div
        id={hubPanelId(view)}
        role="tabpanel"
        className="td-hub-panel flex flex-col gap-3"
        aria-label={activeLabel}
      >
        {view === "portfolio" ? (
          <PortfolioDesk showHeader={false} />
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                className="td-btn td-btn-ghost"
                disabled={loading}
                onClick={() => void refresh()}
              >
                {loading ? "Refreshing…" : "Refresh marks"}
              </button>
              {view === "history" ? (
                <span className="text-[12px]" style={{ color: "var(--td-ink-400)" }}>
                  Closed outcomes and live model stats; no performance is inferred
                  when the ledger is empty.
                </span>
              ) : (
                <span className="text-[12px]" style={{ color: "var(--td-ink-400)" }}>
                  Open risk marked via yfinance (delayed). Close fills the History tab.
                </span>
              )}
            </div>

            {error ? (
              <div className="td-alert td-alert--error" role="alert">
                <strong>Ledger load failed.</strong> {error}
                {" — "}
                Check network, then Refresh marks. If this is a remote deploy,
                confirm the paper ledger API path is available (local monorepo
                or mounted ledger store).
              </div>
            ) : null}

            <div className="td-panel overflow-hidden p-3">
              <PositionsTable
                positions={data?.positions ?? []}
                statsRows={data?.stats.rows ?? []}
                onClose={handleClose}
                onUpdate={handleUpdate}
                onDelete={handleDelete}
                closingId={closingId}
                mode={view === "history" ? "history" : "open"}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default function PositionsPage() {
  return (
    <Suspense
      fallback={
        <div className="td-page">
          <div className="td-panel p-3">Loading portfolio hub…</div>
        </div>
      }
    >
      <PositionsDesk />
    </Suspense>
  );
}
