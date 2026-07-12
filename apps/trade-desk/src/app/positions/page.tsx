"use client";

import { useCallback, useEffect, useState } from "react";

import { PositionsTable } from "@/components/positions/PositionsTable";
import { PageHeader } from "@/components/shell/PageHeader";
import type { ApiEnvelope, PositionsResponse } from "@/lib/types";

export default function PositionsPage() {
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

      <div className="mb-3">
        <button
          type="button"
          className="td-btn td-btn-ghost"
          disabled={loading}
          onClick={() => void refresh()}
        >
          {loading ? "Refreshing…" : "Refresh marks"}
        </button>
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
  );
}
