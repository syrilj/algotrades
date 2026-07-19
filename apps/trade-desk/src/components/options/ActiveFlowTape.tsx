"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Pause, Play, RefreshCw } from "lucide-react";

import type { FlowFeedEntry, OptionsFlowFeed } from "@/lib/flowFeed";
import type { ApiEnvelope } from "@/lib/types";
import { formatNum, formatUsd, sanitizeSymbol } from "@/lib/format";

const REFRESH_MS = 60_000;

const PREMIUM_FILTERS = [
  { label: "All premium", value: 0 },
  { label: "≥ $50K", value: 50_000 },
  { label: "≥ $100K", value: 100_000 },
  { label: "≥ $250K", value: 250_000 },
  { label: "≥ $1M", value: 1_000_000 },
] as const;

type SideFilter = "all" | "C" | "P";

function isCall(right: string | undefined): boolean {
  const u = (right ?? "").toUpperCase();
  return u === "C" || u === "CALL";
}

function compactUsd(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  return formatUsd(value, 0);
}

function printTime(entry: FlowFeedEntry): string {
  if (!entry.trade_time) return "—";
  const d = new Date(entry.trade_time);
  if (!Number.isFinite(d.getTime())) return "—";
  return d.toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: "America/New_York",
  });
}

export function ActiveFlowTape({
  onSelect,
}: {
  onSelect?: (symbol: string) => void;
}) {
  const [feed, setFeed] = useState<OptionsFlowFeed | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(true);
  const [side, setSide] = useState<SideFilter>("all");
  const [minPremium, setMinPremium] = useState<number>(0);
  const [tickerQuery, setTickerQuery] = useState("");
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const inFlight = useRef(false);

  const refresh = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setLoading(true);
    try {
      const res = await fetch("/api/options-flow-feed", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const json = (await res.json()) as ApiEnvelope<OptionsFlowFeed>;
      if (json.data && (json.data.entries.length > 0 || json.ok)) {
        setFeed(json.data);
        setError(json.ok ? null : (json.error ?? null));
      } else {
        throw new Error(json.error ?? `flow feed failed (${res.status})`);
      }
      setLastUpdated(new Date().toISOString());
    } catch (e) {
      setError(e instanceof Error ? e.message : "flow feed failed");
    } finally {
      setLoading(false);
      inFlight.current = false;
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

  const rows = useMemo(() => {
    const entries = feed?.entries ?? [];
    const q = sanitizeSymbol(tickerQuery) ?? "";
    return entries.filter((e) => {
      if (side !== "all" && (isCall(e.right) ? "C" : "P") !== side) return false;
      if ((e.premium ?? 0) < minPremium) return false;
      if (q && !e.symbol.toUpperCase().startsWith(q)) return false;
      return true;
    });
  }, [feed, side, minPremium, tickerQuery]);

  const summary = feed?.summary;
  const bullishPct = summary?.bullish_pct ?? 50;
  const sentimentColor =
    summary?.sentiment === "bullish"
      ? "#8fc39d"
      : summary?.sentiment === "bearish"
        ? "#dc7e76"
        : "var(--td-muted)";
  const failedSymbols = Object.keys(feed?.errors ?? {});

  return (
    <section className="td-panel flex flex-col gap-3 p-5">
      <div className="flex flex-wrap items-start justify-between gap-2 border-b border-[var(--td-hairline)] pb-3">
        <div>
          <span className="td-label uppercase tracking-wider text-[11px] font-semibold text-[var(--td-ink-100)]">
            Active Options Flow · Watchlist Tape
          </span>
          <p className="text-[12px] text-[var(--td-muted)] mt-1">
            Multi-name unusual prints ordered newest first. LSE time-and-sales preferred; chain proxy fallback.
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
            aria-label="Refresh flow"
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {summary && (feed?.entries.length ?? 0) > 0 ? (
        <div className="flex flex-col gap-1.5">
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 font-mono text-[11px]">
            <span style={{ color: sentimentColor }} className="font-bold uppercase tracking-wider">
              {summary.sentiment} · {bullishPct.toFixed(0)}% call premium
            </span>
            <span className="text-[var(--td-muted)]">
              Calls {summary.call_count} · {compactUsd(summary.call_premium)}
              {"  |  "}
              Puts {summary.put_count} · {compactUsd(summary.put_premium)}
              {"  |  "}
              Total {compactUsd(summary.total_premium)}
            </span>
          </div>
          <div
            className="h-1.5 w-full overflow-hidden rounded-full"
            style={{ background: "#A3484866" }}
            role="img"
            aria-label={`Call premium share ${bullishPct.toFixed(0)}%`}
          >
            <div
              className="h-full rounded-full"
              style={{ width: `${bullishPct}%`, background: "#2F6B4F" }}
            />
          </div>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex overflow-hidden rounded border border-[var(--td-hairline)]">
          {(
            [
              ["all", "All"],
              ["C", "Calls"],
              ["P", "Puts"],
            ] as Array<[SideFilter, string]>
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setSide(value)}
              className="px-2.5 py-1 font-mono text-[11px] font-semibold transition-colors"
              style={{
                background:
                  side === value
                    ? value === "C"
                      ? "#2F6B4F33"
                      : value === "P"
                        ? "#A3484833"
                        : "color-mix(in srgb, var(--td-brand) 18%, transparent)"
                    : "transparent",
                color:
                  side === value
                    ? value === "C"
                      ? "#8fc39d"
                      : value === "P"
                        ? "#dc7e76"
                        : "var(--td-ink-100)"
                    : "var(--td-muted)",
              }}
            >
              {label}
            </button>
          ))}
        </div>
        <select
          value={minPremium}
          onChange={(e) => setMinPremium(Number(e.target.value))}
          className="td-input py-1 px-2 text-[11px]"
          style={{ fontFamily: "var(--td-font-mono)", background: "var(--td-surface-soft)" }}
          aria-label="Minimum premium filter"
        >
          {PREMIUM_FILTERS.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </select>
        <input
          value={tickerQuery}
          onChange={(e) => setTickerQuery(e.target.value.toUpperCase())}
          placeholder="Ticker"
          className="td-input py-1 px-2 text-[11px] w-24"
          style={{ fontFamily: "var(--td-font-mono)", background: "var(--td-surface-soft)" }}
          aria-label="Filter by ticker"
        />
        <span className="ml-auto font-mono text-[10px] text-[var(--td-ink-500)]">
          {rows.length} prints
          {lastUpdated
            ? ` · updated ${new Date(lastUpdated).toLocaleTimeString("en-US", { hour12: false })}`
            : ""}
        </span>
      </div>

      {error ? (
        <p className="text-[12px] text-[var(--td-action-avoid)]" role="alert">
          Flow feed: {error.slice(0, 200)}
        </p>
      ) : null}
      {failedSymbols.length > 0 && !error ? (
        <p className="text-[11px]" style={{ color: "var(--td-ink-500)" }}>
          Partial scan — no data for {failedSymbols.join(", ")}.
        </p>
      ) : null}

      {loading && !feed ? (
        <p className="text-[13px] td-muted">Scanning watchlist tape…</p>
      ) : null}

      {!loading && rows.length === 0 && !error ? (
        <p className="text-[13px]" style={{ color: "var(--td-ink-400)" }}>
          No unusual prints match the current filters.
        </p>
      ) : null}

      {rows.length > 0 ? (
        <div className="overflow-x-auto max-h-[480px] overflow-y-auto">
          <table className="w-full text-left text-[12px] border-collapse">
            <thead className="sticky top-0" style={{ background: "var(--td-surface)" }}>
              <tr className="border-b border-[var(--td-hairline)]" style={{ color: "var(--td-ink-400)" }}>
                <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px]">Time</th>
                <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px]">Ticker</th>
                <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px]">C/P</th>
                <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px] text-right">Strike</th>
                <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px]">Expiry</th>
                <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px] text-right">Spot</th>
                <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px] text-right">Size</th>
                <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px] text-right">Price</th>
                <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px] text-right">Premium</th>
                <th className="py-2 font-semibold uppercase tracking-wider text-[10px] text-right">Score</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((f, i) => {
                const call = isCall(f.right);
                const key = `${f.symbol}-${f.expiry}-${f.right}-${f.strike}-${f.trade_time ?? i}`;
                const bigPrint = (f.premium ?? 0) >= 1_000_000;
                return (
                  <tr
                    key={key}
                    className="cursor-pointer hover:bg-[var(--td-surface-soft)] transition-colors"
                    style={{
                      borderBottom: "1px solid var(--td-hairline)",
                      background: call ? "#2F6B4F0D" : "#A348480D",
                    }}
                    onClick={() => onSelect?.(f.symbol)}
                  >
                    <td className="py-2 pr-3 font-mono text-[11px]" style={{ color: "var(--td-ink-400)" }}>
                      {printTime(f)}
                    </td>
                    <td className="py-2 pr-3 font-mono font-bold text-[var(--td-ink)]">{f.symbol}</td>
                    <td className="py-2 pr-3">
                      <span
                        className={`px-1.5 py-0.5 rounded font-mono text-[10px] font-bold ${
                          call ? "bg-[#2F6B4F1A] text-[#8fc39d]" : "bg-[#A348481A] text-[#dc7e76]"
                        }`}
                      >
                        {call ? "CALL" : "PUT"}
                      </span>
                    </td>
                    <td className="py-2 pr-3 font-mono font-semibold text-right text-[var(--td-ink)]">
                      {formatUsd(f.strike)}
                    </td>
                    <td className="py-2 pr-3 font-mono text-[11px]" style={{ color: "var(--td-ink-300)" }}>
                      {f.expiry} · {f.dte}d
                    </td>
                    <td className="py-2 pr-3 font-mono text-right" style={{ color: "var(--td-ink-300)" }}>
                      {f.spot != null ? formatUsd(f.spot) : "—"}
                    </td>
                    <td className="py-2 pr-3 font-mono text-right text-[var(--td-ink)]">
                      {formatNum(f.volume, 0)}
                    </td>
                    <td className="py-2 pr-3 font-mono text-right" style={{ color: "var(--td-ink-300)" }}>
                      {f.mid != null ? formatUsd(f.mid) : "—"}
                    </td>
                    <td
                      className="py-2 pr-3 font-mono font-bold text-right"
                      style={{ color: bigPrint ? (call ? "#8fc39d" : "#dc7e76") : "var(--td-ink)" }}
                    >
                      {compactUsd(f.premium)}
                    </td>
                    <td className="py-2 font-mono text-right" style={{ color: "var(--td-ink-400)" }}>
                      {formatNum(f.score, 0)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}

      <div className="flex justify-between items-center text-[11px] text-[var(--td-muted)]">
        <span>
          Watching {feed?.symbols.join(", ") ?? "watchlist"} · click a print to load its ticket.
        </span>
        {feed?.asof_utc ? <span>As-of {feed.asof_utc}</span> : null}
      </div>
    </section>
  );
}
