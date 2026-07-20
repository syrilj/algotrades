"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Pause, Play, RefreshCw } from "lucide-react";

import type {
  ApiEnvelope,
  DarkPoolPrint,
  DarkPoolResponse,
} from "@/lib/types";
import { formatNum, formatPct, formatUsd, sanitizeSymbol } from "@/lib/format";
import { PageHeader } from "@/components/shell/PageHeader";
import { analyzeHref } from "@/lib/routes";

const REFRESH_MS = 60_000;

function compactUsd(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  return formatUsd(value, 0);
}

export function DarkPoolDesk({ showHeader = true }: { showHeader?: boolean }) {
  const [data, setData] = useState<DarkPoolResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(true);
  const [symbol, setSymbol] = useState("");
  const [minNotional, setMinNotional] = useState(1_000_000);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const body: Record<string, unknown> = { minNotional };
      const s = sanitizeSymbol(symbol);
      if (s) body.symbol = s;

      const res = await fetch("/api/dark-pool", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const json = (await res.json()) as ApiEnvelope<DarkPoolResponse>;
      if (!res.ok || json.ok === false || !json.data) {
        throw new Error(json.error ?? `dark pool failed (${res.status})`);
      }
      setData(json.data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "dark pool failed");
    } finally {
      setLoading(false);
    }
  }, [symbol, minNotional]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!live) return;
    const id = setInterval(() => void refresh(), REFRESH_MS);
    return () => clearInterval(id);
  }, [live, refresh]);

  const prints = useMemo(() => data?.prints ?? [], [data]);
  const filtered = useMemo(() => {
    let rows = prints;
    const s = sanitizeSymbol(symbol);
    if (s) rows = rows.filter((p) => p.symbol.toUpperCase().startsWith(s));
    if (minNotional > 0) rows = rows.filter((p) => p.notional >= minNotional);
    return rows;
  }, [prints, symbol, minNotional]);

  const body = (
    <>
      {showHeader ? (
        <PageHeader
          title="Dark Pool Prints"
          description="Off-exchange equity trades from FINRA TRF/ADF venues, tagged vs the lit market."
        />
      ) : null}

      <section className="td-panel flex flex-col gap-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-2 border-b border-[var(--td-hairline)] pb-3">
          <div>
            <span className="td-label uppercase tracking-wider text-[11px] font-semibold text-[var(--td-ink-100)]">
              Off-exchange tape
            </span>
            <p className="text-[12px] text-[var(--td-muted)] mt-1">
              Requires a stocks-trades feed or FINRA TRF/ADF source. This desk is wired and ready once data is connected.
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
              aria-label="Refresh dark pool"
            >
              <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
            </button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            onBlur={() => void refresh()}
            onKeyDown={(e) => {
              if (e.key === "Enter") void refresh();
            }}
            placeholder="Symbol"
            className="td-input py-1 px-2 text-[11px] w-28"
            style={{ fontFamily: "var(--td-font-mono)", background: "var(--td-surface-soft)" }}
            aria-label="Filter by symbol"
          />
          <select
            value={minNotional}
            onChange={(e) => {
              setMinNotional(Number(e.target.value));
              void refresh();
            }}
            className="td-input py-1 px-2 text-[11px]"
            style={{ fontFamily: "var(--td-font-mono)", background: "var(--td-surface-soft)" }}
            aria-label="Minimum notional filter"
          >
            <option value={100_000}>≥ $100K</option>
            <option value={500_000}>≥ $500K</option>
            <option value={1_000_000}>≥ $1M</option>
            <option value={5_000_000}>≥ $5M</option>
          </select>
        </div>

        {error ? (
          <p className="text-[12px] text-[var(--td-action-avoid)]" role="alert">
            {error}
          </p>
        ) : null}

        {data?.note ? (
          <p className="text-[13px]" style={{ color: "var(--td-ink-400)" }}>
            {data.note}
          </p>
        ) : null}

        {loading && !data ? (
          <p className="text-[13px] td-muted">Loading dark pool feed…</p>
        ) : null}

        {!loading && filtered.length === 0 ? (
          <p className="text-[13px]" style={{ color: "var(--td-ink-400)" }}>
            No dark pool prints match the current filters. Wire a feed to populate this desk.
          </p>
        ) : null}

        {filtered.length > 0 ? (
          <div className="overflow-x-auto max-h-[560px] overflow-y-auto">
            <table className="w-full text-left text-[12px] border-collapse">
              <thead className="sticky top-0" style={{ background: "var(--td-surface)" }}>
                <tr className="border-b border-[var(--td-hairline)]" style={{ color: "var(--td-ink-400)" }}>
                  <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px]">Time</th>
                  <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px]">Symbol</th>
                  <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px] text-right">Price</th>
                  <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px] text-right">Size</th>
                  <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px] text-right">Notional</th>
                  <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px]">vs Lit</th>
                  <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px] text-right">% ADV</th>
                  <th className="py-2 font-semibold uppercase tracking-wider text-[10px]">Action</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((p: DarkPoolPrint, i) => (
                  <tr
                    key={`${p.symbol}-${p.ts}-${i}`}
                    className="hover:bg-[var(--td-surface-soft)] transition-colors"
                    style={{ borderBottom: "1px solid var(--td-hairline)" }}
                  >
                    <td className="py-2.5 pr-3 font-mono text-[11px] text-[var(--td-ink-400)]">
                      {p.ts ? new Date(p.ts).toLocaleTimeString("en-US", { hour12: false, timeZone: "America/New_York" }) : "—"}
                    </td>
                    <td className="py-2.5 pr-3 font-mono font-bold text-[var(--td-ink)]">{p.symbol}</td>
                    <td className="py-2.5 pr-3 font-mono text-right">{formatUsd(p.price)}</td>
                    <td className="py-2.5 pr-3 font-mono text-right">{formatNum(p.size, 0)}</td>
                    <td className="py-2.5 pr-3 font-mono text-right font-semibold">{compactUsd(p.notional)}</td>
                    <td className="py-2.5 pr-3 font-mono">
                      <span
                        className="px-1.5 py-0.5 text-[10px] font-bold uppercase"
                        style={{
                          color:
                            p.vs_market === "above"
                              ? "#8fc39d"
                              : p.vs_market === "below"
                                ? "#dc7e76"
                                : "var(--td-muted)",
                          border: "1px solid var(--td-hairline)",
                        }}
                      >
                        {p.vs_market}
                      </span>
                    </td>
                    <td className="py-2.5 pr-3 font-mono text-right">{formatPct(p.pct_adv ?? 0, 1)}</td>
                    <td className="py-2.5">
                      <Link
                        href={analyzeHref({ symbol: p.symbol })}
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
