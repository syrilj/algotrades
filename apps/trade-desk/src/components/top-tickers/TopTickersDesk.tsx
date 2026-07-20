"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Pause, Play, RefreshCw } from "lucide-react";

import type {
  ApiEnvelope,
  TopTickerRow,
  TopTickersResponse,
} from "@/lib/types";
import { formatNum, formatUsd } from "@/lib/format";
import { PageHeader } from "@/components/shell/PageHeader";
import { Chip } from "@/components/ui/Chip";
import { analyzeHref } from "@/lib/routes";
import { colorVarFor } from "@/lib/actionColors";

const REFRESH_MS = 60_000;

function compactUsd(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  return formatUsd(value, 0);
}

function SentimentBadge({ row }: { row: TopTickerRow }) {
  const color =
    row.sentiment === "bullish"
      ? colorVarFor("mode", "OPTIONS_ATTACK")
      : row.sentiment === "bearish"
        ? colorVarFor("mode", "STAND_ASIDE")
        : colorVarFor("mode", "WAIT");
  return (
    <Chip
      label={`${row.sentiment} · ${row.bullish_pct.toFixed(0)}% calls`}
      colorVar={color}
    />
  );
}

export function TopTickersDesk({ showHeader = true }: { showHeader?: boolean }) {
  const [data, setData] = useState<TopTickersResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(true);
  const [activeKey, setActiveKey] = useState<string>("premium");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/top-tickers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ limit: 15 }),
      });
      const json = (await res.json()) as ApiEnvelope<TopTickersResponse>;
      if (!res.ok || json.ok === false || !json.data) {
        throw new Error(json.error ?? `top tickers failed (${res.status})`);
      }
      const data = json.data;
      setData(data);
      setActiveKey((prev) =>
        data.categories.find((c) => c.key === prev)
          ? prev
          : (data.categories[0]?.key ?? "premium"),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "top tickers failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!live) return;
    const id = setInterval(() => void refresh(), REFRESH_MS);
    return () => clearInterval(id);
  }, [live, refresh]);

  const activeCategory = useMemo(
    () => data?.categories.find((c) => c.key === activeKey),
    [data, activeKey],
  );

  const body = (
    <>
      {showHeader ? (
        <PageHeader
          title="Top Tickers"
          description="Ranked discovery from live options flow: premium, unusual score, activity, and short-dated urgency."
        />
      ) : null}

      <section className="td-panel flex flex-col gap-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-2 border-b border-[var(--td-hairline)] pb-3">
          <div>
            <span className="td-label uppercase tracking-wider text-[11px] font-semibold text-[var(--td-ink-100)]">
              Flow-based discovery
            </span>
            <p className="text-[12px] text-[var(--td-muted)] mt-1">
              Aggregated from the multi-symbol options tape. True sweep/block tags require OPRA condition codes.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span
              className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-wider"
              style={{ color: live ? "#8fc39d" : "var(--td-muted)" }}
            >
              <span
                className={`w-2 h-2 rounded-full ${live ? "animate-pulse" : ""}`}
                style={{ background: "currentcolor" }}
              />
              {live ? "LIVE" : "PAUSED"}
            </span>
            <button
              type="button"
              className="td-btn td-btn-ghost"
              onClick={() => setLive((v) => !v)}
              aria-label={live ? "Pause auto-refresh" : "Resume auto-refresh"}
            >
              {live ? <Pause size={13} /> : <Play size={13} />}
            </button>
            <button
              type="button"
              className="td-btn td-btn-ghost"
              onClick={() => void refresh()}
              disabled={loading}
              aria-label="Refresh top tickers"
            >
              <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
            </button>
          </div>
        </div>

        {error ? (
          <p className="text-[12px] text-[var(--td-action-avoid)]" role="alert">
            {error}
          </p>
        ) : null}

        {data?.note ? (
          <p className="text-[11px]" style={{ color: "var(--td-ink-500)" }}>
            {data.note}
          </p>
        ) : null}

        {data && data.categories.length > 0 ? (
          <div className="flex flex-wrap gap-1" role="tablist" aria-label="Top ticker categories">
            {data.categories.map((c) => {
              const active = c.key === activeKey;
              return (
                <button
                  key={c.key}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => setActiveKey(c.key)}
                  className="px-2.5 py-1.5 font-mono text-[11px] font-semibold transition-colors"
                  style={{
                    background: active
                      ? "color-mix(in srgb, var(--td-brand) 18%, transparent)"
                      : "transparent",
                    color: active ? "var(--td-ink-100)" : "var(--td-muted)",
                    border: "1px solid var(--td-hairline)",
                  }}
                >
                  {c.label}
                </button>
              );
            })}
          </div>
        ) : null}

        {activeCategory ? (
          <div className="text-[12px]" style={{ color: "var(--td-muted)" }}>
            {activeCategory.description}
          </div>
        ) : null}

        {loading && !data ? (
          <p className="text-[13px] td-muted">Loading top tickers…</p>
        ) : null}

        {!loading && activeCategory?.rows.length === 0 ? (
          <p className="text-[13px]" style={{ color: "var(--td-ink-400)" }}>
            No tickers match the current filters.
          </p>
        ) : null}

        {activeCategory && activeCategory.rows.length > 0 ? (
          <div className="overflow-x-auto max-h-[560px] overflow-y-auto">
            <table className="w-full text-left text-[12px] border-collapse">
              <thead className="sticky top-0" style={{ background: "var(--td-surface)" }}>
                <tr className="border-b border-[var(--td-hairline)]" style={{ color: "var(--td-ink-400)" }}>
                  <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px]">Rank</th>
                  <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px]">Symbol</th>
                  <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px] text-right">Total Premium</th>
                  <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px] text-right">Flags</th>
                  <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px] text-right">Avg Score</th>
                  <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px] text-right">Short-DTE Premium</th>
                  <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px]">Sentiment</th>
                  <th className="py-2 font-semibold uppercase tracking-wider text-[10px]">Action</th>
                </tr>
              </thead>
              <tbody>
                {activeCategory.rows.map((row) => (
                  <tr
                    key={row.symbol}
                    className="hover:bg-[var(--td-surface-soft)] transition-colors"
                    style={{ borderBottom: "1px solid var(--td-hairline)" }}
                  >
                    <td className="py-2.5 pr-3 font-mono text-[var(--td-ink-300)]">{row.rank}</td>
                    <td className="py-2.5 pr-3 font-mono font-bold text-[var(--td-ink)]">{row.symbol}</td>
                    <td className="py-2.5 pr-3 font-mono text-right">{compactUsd(row.total_premium)}</td>
                    <td className="py-2.5 pr-3 font-mono text-right">{formatNum(row.flag_count, 0)}</td>
                    <td className="py-2.5 pr-3 font-mono text-right">{formatNum(row.avg_score, 0)}</td>
                    <td className="py-2.5 pr-3 font-mono text-right">{compactUsd(row.short_dte_premium)}</td>
                    <td className="py-2.5 pr-3">
                      <SentimentBadge row={row} />
                    </td>
                    <td className="py-2.5">
                      <Link
                        href={analyzeHref({ symbol: row.symbol })}
                        className="td-btn td-btn-ghost no-underline"
                      >
                        Analyze
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        {data?.asof_utc ? (
          <div className="text-[11px] text-[var(--td-muted)]">
            As-of {data.asof_utc}
          </div>
        ) : null}
      </section>
    </>
  );

  return showHeader ? <div className="td-page">{body}</div> : body;
}
