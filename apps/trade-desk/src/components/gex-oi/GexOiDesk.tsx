"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Pause, Play, RefreshCw } from "lucide-react";

import type { ApiEnvelope, GammaResponse, GammaStrike } from "@/lib/types";
import {
  formatNum,
  formatPctPointsUnsigned,
  formatUsd,
} from "@/lib/format";
import { PageHeader } from "@/components/shell/PageHeader";
import { analyzeHref, gammaHref } from "@/lib/routes";

const REFRESH_MS = 60_000;

function compactUsd(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(2)}B`;
  if (abs >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  return formatUsd(value, 0);
}

function signedGex(value: number): string {
  if (!Number.isFinite(value)) return "—";
  return `${value > 0 ? "+" : value < 0 ? "-" : ""}${compactUsd(Math.abs(value))}`;
}

export function GexOiDesk({
  symbol: initialSymbol,
  showHeader = true,
}: {
  symbol?: string;
  showHeader?: boolean;
}) {
  const [symbol, setSymbol] = useState((initialSymbol || "APLD").toUpperCase());
  const [data, setData] = useState<GammaResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(true);
  const [activeTab, setActiveTab] = useState<"gex" | "oi">("gex");

  const refresh = useCallback(async (sym?: string) => {
    const s = (sym ?? symbol).trim().toUpperCase();
    if (!s) return;
    setSymbol(s);
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/gamma", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: s, source: "auto" }),
      });
      const json = (await res.json()) as ApiEnvelope<GammaResponse>;
      if (!res.ok || json.ok === false || !json.data) {
        throw new Error(json.error ?? `GEX/OI failed (${res.status})`);
      }
      setData(json.data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "GEX/OI failed");
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  useEffect(() => {
    void refresh(initialSymbol);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialSymbol]);

  useEffect(() => {
    if (!live) return;
    const id = setInterval(() => void refresh(), REFRESH_MS);
    return () => clearInterval(id);
  }, [live, refresh]);

  const byStrike = useMemo(() => {
    const rows = data?.by_strike ?? [];
    return rows
      .slice()
      .sort((a, b) => a.strike - b.strike);
  }, [data]);

  const maxAbsGex = useMemo(() => {
    return Math.max(
      1,
      ...byStrike.map((r) => Math.max(Math.abs(r.call_gex), Math.abs(r.put_gex), Math.abs(r.net_gex))),
    );
  }, [byStrike]);

  const levelDistance = (value: number | null | undefined): string => {
    if (value == null || data?.spot == null) return "—";
    const d = ((value - data.spot) / data.spot) * 100;
    return `${d > 0 ? "+" : ""}${d.toFixed(1)}%`;
  };

  const body = (
    <>
      {showHeader ? (
        <PageHeader
          title="GEX / OI"
          description="Gamma exposure and open-interest levels by strike. Dealer-side convention: calls positive, puts negative."
        />
      ) : null}

      <section className="td-panel flex flex-col gap-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-2 border-b border-[var(--td-hairline)] pb-3">
          <div>
            <span className="td-label uppercase tracking-wider text-[11px] font-semibold text-[var(--td-ink-100)]">
              Gamma + open interest
            </span>
            <p className="text-[12px] text-[var(--td-muted)] mt-1">
              Spot dealer gamma by strike and key OI-based structural levels.
            </p>
          </div>
          <div className="flex items-center gap-2">
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
              aria-label="Symbol"
            />
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
              aria-label="Refresh GEX/OI"
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

        {data && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <div className="border p-3" style={{ borderColor: "var(--td-hairline)", background: "var(--td-canvas)" }}>
              <div className="text-[10px] uppercase tracking-wider" style={{ color: "var(--td-ink-500)" }}>Spot</div>
              <div className="mt-1 tabular text-[15px] font-semibold" style={{ fontFamily: "var(--td-font-mono)" }}>{formatUsd(data.spot)}</div>
            </div>
            <div className="border p-3" style={{ borderColor: "var(--td-hairline)", background: "var(--td-canvas)" }}>
              <div className="text-[10px] uppercase tracking-wider" style={{ color: "var(--td-ink-500)" }}>Net GEX</div>
              <div className="mt-1 tabular text-[15px] font-semibold" style={{ fontFamily: "var(--td-font-mono)", color: data.net_dealer_gex > 0 ? "#8fc39d" : data.net_dealer_gex < 0 ? "#dc7e76" : "var(--td-ink-300)" }}>
                {signedGex(data.net_dealer_gex)}
              </div>
            </div>
            <div className="border p-3" style={{ borderColor: "var(--td-hairline)", background: "var(--td-canvas)" }}>
              <div className="text-[10px] uppercase tracking-wider" style={{ color: "var(--td-ink-500)" }}>Regime</div>
              <div className="mt-1 tabular text-[15px] font-semibold uppercase" style={{ fontFamily: "var(--td-font-mono)" }}>{data.regime.replace(/_/g, " ")}</div>
            </div>
            <div className="border p-3" style={{ borderColor: "var(--td-hairline)", background: "var(--td-canvas)" }}>
              <div className="text-[10px] uppercase tracking-wider" style={{ color: "var(--td-ink-500)" }}>Total OI</div>
              <div className="mt-1 tabular text-[15px] font-semibold" style={{ fontFamily: "var(--td-font-mono)" }}>{data.total_oi != null ? formatNum(data.total_oi, 0) : "—"}</div>
            </div>
          </div>
        )}

        <div className="flex flex-wrap gap-1" role="tablist" aria-label="GEX/OI view">
          {(["gex", "oi"] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              role="tab"
              aria-selected={activeTab === tab}
              onClick={() => setActiveTab(tab)}
              className="px-2.5 py-1.5 font-mono text-[11px] font-semibold transition-colors"
              style={{
                background: activeTab === tab
                  ? "color-mix(in srgb, var(--td-brand) 18%, transparent)"
                  : "transparent",
                color: activeTab === tab ? "var(--td-ink-100)" : "var(--td-muted)",
                border: "1px solid var(--td-hairline)",
              }}
            >
              {tab === "gex" ? "GEX by strike" : "OI levels"}
            </button>
          ))}
        </div>

        {loading && !data ? (
          <p className="text-[13px] td-muted">Loading GEX/OI…</p>
        ) : null}

        {activeTab === "gex" && data ? (
          <div className="overflow-x-auto max-h-[560px] overflow-y-auto">
            <table className="w-full text-left text-[12px] border-collapse">
              <thead className="sticky top-0" style={{ background: "var(--td-surface)" }}>
                <tr className="border-b border-[var(--td-hairline)]" style={{ color: "var(--td-ink-400)" }}>
                  <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px]">Strike</th>
                  <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px] text-right">Call GEX</th>
                  <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px] text-right">Put GEX</th>
                  <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px] text-right">Net GEX</th>
                  <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px]">Visual</th>
                </tr>
              </thead>
              <tbody>
                {byStrike.map((row: GammaStrike) => {
                  const isSpot = data.spot != null && Math.abs(row.strike - data.spot) / data.spot < 0.005;
                  const netColor = row.net_gex > 0 ? "#8fc39d" : row.net_gex < 0 ? "#dc7e76" : "var(--td-muted)";
                  const barWidth = `${Math.min(100, (Math.abs(row.net_gex) / maxAbsGex) * 100)}%`;
                  return (
                    <tr
                      key={row.strike}
                      className="hover:bg-[var(--td-surface-soft)] transition-colors"
                      style={{
                        borderBottom: "1px solid var(--td-hairline)",
                        background: isSpot ? "color-mix(in srgb, var(--td-brand) 8%, transparent)" : undefined,
                      }}
                    >
                      <td className="py-2 pr-3 font-mono font-bold text-[var(--td-ink)]">
                        {formatUsd(row.strike)}
                        {isSpot ? " · spot" : null}
                      </td>
                      <td className="py-2 pr-3 font-mono text-right" style={{ color: "#8fc39d" }}>{signedGex(row.call_gex)}</td>
                      <td className="py-2 pr-3 font-mono text-right" style={{ color: "#dc7e76" }}>{signedGex(row.put_gex)}</td>
                      <td className="py-2 pr-3 font-mono text-right font-semibold" style={{ color: netColor }}>{signedGex(row.net_gex)}</td>
                      <td className="py-2 pr-3">
                        <div className="h-1.5 w-24 overflow-hidden" style={{ background: "var(--td-surface-elevated)" }}>
                          <div
                            className="h-full"
                            style={{
                              width: barWidth,
                              background: netColor,
                              marginLeft: row.net_gex >= 0 ? 0 : `calc(100% - ${barWidth})`,
                            }}
                          />
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}

        {activeTab === "oi" && data ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <LevelCard
              label="Call wall"
              value={data.call_wall}
              distance={levelDistance(data.call_wall)}
              detail={data.call_wall_gex != null ? `GEX ${compactUsd(data.call_wall_gex)}` : undefined}
            />
            <LevelCard
              label="Put wall"
              value={data.put_wall}
              distance={levelDistance(data.put_wall)}
              detail={data.put_wall_gex != null ? `GEX ${compactUsd(data.put_wall_gex)}` : undefined}
            />
            <LevelCard
              label="Max pain"
              value={data.max_pain}
              distance={levelDistance(data.max_pain)}
            />
            <LevelCard
              label="Gamma flip"
              value={data.approx_flip_strike}
              distance={levelDistance(data.approx_flip_strike)}
            />
            <div className="border p-3" style={{ borderColor: "var(--td-hairline)", background: "var(--td-canvas)" }}>
              <div className="text-[10px] uppercase tracking-wider" style={{ color: "var(--td-ink-500)" }}>Expected move</div>
              <div className="mt-1 tabular text-[15px] font-semibold" style={{ fontFamily: "var(--td-font-mono)" }}>
                {data.expected_move_pct != null
                  ? `±${formatPctPointsUnsigned(data.expected_move_pct)} (${formatUsd(data.expected_move_low)} - ${formatUsd(data.expected_move_high)})`
                  : "—"}
              </div>
            </div>
            <div className="border p-3" style={{ borderColor: "var(--td-hairline)", background: "var(--td-canvas)" }}>
              <div className="text-[10px] uppercase tracking-wider" style={{ color: "var(--td-ink-500)" }}>OI split</div>
              <div className="mt-1 tabular text-[15px] font-semibold" style={{ fontFamily: "var(--td-font-mono)" }}>
                Calls {data.otm_call_oi != null ? formatNum(data.otm_call_oi, 0) : "—"} · Puts {data.otm_put_oi != null ? formatNum(data.otm_put_oi, 0) : "—"}
              </div>
            </div>
          </div>
        ) : null}

        {!data && !loading ? (
          <p className="text-[13px]" style={{ color: "var(--td-ink-400)" }}>
            Enter a symbol above to load GEX and OI levels.
          </p>
        ) : null}

        {data && (
          <div className="flex flex-wrap gap-2">
            <Link href={analyzeHref({ symbol })} className="td-btn td-btn-ghost no-underline">
              Analyze
            </Link>
            <Link href={gammaHref(symbol)} className="td-btn td-btn-ghost no-underline">
              Gamma desk
            </Link>
          </div>
        )}
      </section>
    </>
  );

  return showHeader ? <div className="td-page">{body}</div> : body;
}

function LevelCard({
  label,
  value,
  distance,
  detail,
}: {
  label: string;
  value: number | null;
  distance: string;
  detail?: string;
}) {
  return (
    <div className="border p-3" style={{ borderColor: "var(--td-hairline)", background: "var(--td-canvas)" }}>
      <div className="text-[10px] uppercase tracking-wider" style={{ color: "var(--td-ink-500)" }}>{label}</div>
      <div className="mt-1 tabular text-[15px] font-semibold" style={{ fontFamily: "var(--td-font-mono)" }}>
        {value != null ? formatUsd(value) : "—"}
      </div>
      <div className="mt-1 text-[11px]" style={{ color: "var(--td-muted)" }}>
        {distance} {detail ? `· ${detail}` : ""}
      </div>
    </div>
  );
}
