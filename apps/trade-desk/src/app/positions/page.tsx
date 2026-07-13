"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { PortfolioDesk } from "@/components/portfolio/PortfolioDesk";
import { PositionsTable } from "@/components/positions/PositionsTable";
import { PageHeader } from "@/components/shell/PageHeader";
import type { ApiEnvelope, PositionsResponse } from "@/lib/types";

type PositionsView = "open" | "portfolio" | "history";

function PositionsDesk() {
  const searchParams = useSearchParams();
  const rawView = searchParams.get("view");
  const view: PositionsView = rawView === "portfolio" || rawView === "history" ? rawView : "open";
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
    void refresh();
  }, [refresh]);

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

  return (
    <div className="td-page">
      <PageHeader
        title="Positions"
        description="Paper ledger — open risk marked via yfinance (delayed). Closed outcomes feed model findings."
        meta={
          data?.asof ? (
            <span className="tabular" style={{ fontFamily: "var(--td-font-mono)" }}>
              asof {data.asof.slice(0, 19).replace("T", " ")}Z
              {data.marked ? " · marks refreshed" : null}
            </span>
          ) : null
        }
      />

      <nav className="mb-4 flex flex-wrap gap-1 border-b border-[var(--td-ink-700)]" aria-label="Positions views" role="tablist">
        {([
          ["open", "Open Positions", "/positions"],
          ["portfolio", "Portfolio", "/positions?view=portfolio"],
          ["history", "History / Risk", "/positions?view=history"],
        ] as const).map(([key, label, href]) => (
          <Link
            key={key}
            href={href}
            className={`td-btn ${view === key ? "td-btn-primary" : "td-btn-ghost"}`}
            role="tab"
            aria-selected={view === key}
            aria-controls={`positions-panel-${key}`}
          >
            {label}
          </Link>
        ))}
      </nav>

      {view === "portfolio" ? (
        <div id="positions-panel-portfolio" role="tabpanel">
          <PortfolioDesk />
        </div>
      ) : (
        <div id={`positions-panel-${view}`} role="tabpanel">
          <div className="mb-3 flex flex-wrap items-center gap-2">
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
                Closed outcomes and live model stats; no performance is inferred when the ledger is empty.
              </span>
            ) : null}
          </div>

          {error ? (
            <div className="td-alert td-alert--error mb-3" role="alert">
              {error}
            </div>
          ) : null}

          <div className="td-panel overflow-hidden p-3">
            <PositionsTable
              positions={data?.positions ?? []}
              statsRows={data?.stats.rows ?? []}
              onClose={handleClose}
              closingId={closingId}
            />
          </div>
        </div>
      )}
    </div>
  );
}

export default function PositionsPage() {
  return (
    <Suspense fallback={<div className="td-page"><div className="td-panel p-3">Loading positions hub…</div></div>}>
      <PositionsDesk />
    </Suspense>
  );
}
