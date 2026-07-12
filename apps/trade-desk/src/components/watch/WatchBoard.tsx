"use client";

import { useRouter } from "next/navigation";
import { AlertTriangle, Radio } from "lucide-react";
import { ActionChip, actionRailColor } from "@/components/ui/ActionChip";

export type WatchBoardRow = {
  symbol: string;
  action: string;
  price: number;
  confidence?: number;
  hitProbability?: number;
  stop?: number;
  rvol?: number;
  model?: string;
  volSurge?: boolean;
  volDry?: boolean;
};

type WatchBoardProps = {
  rows: WatchBoardRow[];
  alerts?: string[];
  lastTick?: string | null;
  loading?: boolean;
  error?: string | null;
  emptyHint?: string;
  onSelectSymbol?: (sym: string) => void;
};

function fmtPrice(n: number | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function fmtPct(n: number | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  const v = n <= 1 ? n * 100 : n;
  return `${Math.round(v)}%`;
}

function fmtRvol(row: WatchBoardRow): string {
  if (row.volDry) return "dry";
  if (row.rvol == null || Number.isNaN(row.rvol)) return "—";
  const base = row.rvol.toFixed(1);
  return row.volSurge ? `${base}↑` : base;
}

export function WatchBoard({
  rows,
  alerts = [],
  lastTick,
  loading = false,
  error = null,
  emptyHint = "Add symbols and press Start to poll the watch board.",
  onSelectSymbol,
}: WatchBoardProps) {
  const router = useRouter();

  const select = (sym: string) => {
    if (onSelectSymbol) onSelectSymbol(sym);
    else router.push(`/analyze?symbol=${encodeURIComponent(sym)}`);
  };

  if (error) {
    return (
      <div className="flex items-start gap-2 border border-[var(--td-action-avoid,#A34848)]/40 bg-[var(--td-action-avoid,#A34848)]/10 px-4 py-3 text-[13px] text-[var(--td-ink-100,#E2E8F0)]">
        <AlertTriangle
          className="mt-0.5 size-4 shrink-0 text-[#A34848]"
          strokeWidth={1.75}
        />
        <div>
          <div className="font-medium">Watch failed</div>
          <div className="text-[var(--td-ink-300,#94A3B8)]">{error}</div>
        </div>
      </div>
    );
  }

  if (!rows.length && !loading) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 px-4 py-16 text-center">
        <Radio
          className="size-8 text-[var(--td-ink-500,#475569)]"
          strokeWidth={1.75}
        />
        <p className="font-[family-name:var(--td-font-display,ui-serif,Georgia,serif)] text-xl text-[var(--td-ink-100,#E2E8F0)]">
          No ticks yet
        </p>
        <p className="max-w-sm text-[13px] text-[var(--td-ink-400,#64748B)]">
          {emptyHint}
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-left text-[13px]">
          <thead className="sticky top-0 z-10 bg-[var(--td-ink-700,#243040)]">
            <tr className="border-b border-[var(--td-ink-600,#334155)] text-[11px] font-medium uppercase tracking-wide text-[var(--td-ink-300,#94A3B8)]">
              <th className="px-3 py-2">Sym</th>
              <th className="px-3 py-2">Action</th>
              <th className="px-3 py-2 text-right">Price</th>
              <th className="px-3 py-2 text-right">Conf</th>
              <th className="px-3 py-2 text-right">Hit%</th>
              <th className="px-3 py-2 text-right">Stop</th>
              <th className="px-3 py-2 text-right">RVOL</th>
              <th className="px-3 py-2">Model</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const rail = actionRailColor(row.action);
              return (
                <tr
                  key={row.symbol}
                  onClick={() => select(row.symbol)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      select(row.symbol);
                    }
                  }}
                  tabIndex={0}
                  role="link"
                  className="cursor-pointer border-b border-[var(--td-ink-600,#334155)]/60 bg-[var(--td-ink-900,#12181F)] transition-colors hover:bg-[var(--td-brand-soft,#2F6F7A26)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--td-brand,#2F6F7A)]"
                  style={{ boxShadow: `inset 3px 0 0 ${rail}` }}
                >
                  <td className="px-3 py-2 font-[family-name:var(--td-font-mono,ui-monospace,Menlo,monospace)] font-medium tabular-nums text-[var(--td-ink-100,#E2E8F0)]">
                    {row.symbol}
                  </td>
                  <td className="px-3 py-2">
                    <ActionChip action={row.action} />
                  </td>
                  <td className="px-3 py-2 text-right font-[family-name:var(--td-font-mono,ui-monospace,Menlo,monospace)] tabular-nums text-[var(--td-ink-200,#CBD5E1)]">
                    {fmtPrice(row.price)}
                  </td>
                  <td className="px-3 py-2 text-right font-[family-name:var(--td-font-mono,ui-monospace,Menlo,monospace)] tabular-nums text-[var(--td-ink-200,#CBD5E1)]">
                    {fmtPct(row.confidence)}
                  </td>
                  <td className="px-3 py-2 text-right font-[family-name:var(--td-font-mono,ui-monospace,Menlo,monospace)] tabular-nums text-[var(--td-ink-200,#CBD5E1)]">
                    {fmtPct(row.hitProbability)}
                  </td>
                  <td className="px-3 py-2 text-right font-[family-name:var(--td-font-mono,ui-monospace,Menlo,monospace)] tabular-nums text-[var(--td-ink-200,#CBD5E1)]">
                    {fmtPrice(row.stop)}
                  </td>
                  <td className="px-3 py-2 text-right font-[family-name:var(--td-font-mono,ui-monospace,Menlo,monospace)] tabular-nums text-[var(--td-ink-200,#CBD5E1)]">
                    {fmtRvol(row)}
                  </td>
                  <td className="max-w-[140px] truncate px-3 py-2 text-[var(--td-ink-300,#94A3B8)]">
                    {row.model || "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-[var(--td-ink-600,#334155)] bg-[var(--td-ink-800,#1A222C)] px-3 py-2 text-[11px] text-[var(--td-ink-400,#64748B)]">
        <span>
          last tick{" "}
          <span className="tabular-nums text-[var(--td-ink-300,#94A3B8)]">
            {lastTick
              ? new Date(lastTick).toLocaleTimeString(undefined, {
                  hour12: false,
                })
              : loading
                ? "…"
                : "—"}
          </span>
        </span>
        {loading ? (
          <span className="text-[var(--td-brand,#2F6F7A)]">refreshing</span>
        ) : null}
        {alerts.length > 0 ? (
          <span className="text-[var(--td-ink-300,#94A3B8)]">
            alerts: {alerts.join(" · ")}
          </span>
        ) : null}
      </div>
    </div>
  );
}
