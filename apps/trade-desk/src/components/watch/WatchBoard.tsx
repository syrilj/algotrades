"use client";

import { useRouter } from "next/navigation";
import { AlertTriangle, Radio } from "lucide-react";
import { ActionChip, actionRailColor } from "@/components/ui/ActionChip";
import { EmptyState } from "@/components/ui/EmptyState";
import { analyzeHref } from "@/lib/routes";
import { formatNum, formatPct } from "@/lib/format";

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
  emptyHint = "Add symbols (e.g. NVDA, MU, APLD) and press Start. Click a row → Analyze.",
  onSelectSymbol,
}: WatchBoardProps) {
  const router = useRouter();

  const select = (sym: string) => {
    if (onSelectSymbol) onSelectSymbol(sym);
    else router.push(analyzeHref({ symbol: sym }));
  };

  if (error) {
    return (
      <div className="td-alert td-alert--error flex items-start gap-2" role="alert">
        <AlertTriangle
          className="mt-0.5 size-4 shrink-0"
          strokeWidth={1.75}
          style={{ color: "var(--td-action-avoid)" }}
        />
        <div>
          <div className="font-medium">Watch failed</div>
          <div style={{ color: "var(--td-ink-300)" }}>{error}</div>
        </div>
      </div>
    );
  }

  if (!rows.length && !loading) {
    return <EmptyState icon={Radio} title="No ticks yet" hint={emptyHint} />;
  }

  return (
    <div className="flex flex-col">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-left text-[13px]">
          <thead className="sticky top-0 z-10 bg-[var(--td-canvas,#000000)]">
            <tr className="border-b border-[var(--td-border,#3c3c3c)] text-[11px] font-medium uppercase tracking-wide text-[var(--td-ink-300,#e6e6e6)]">
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
                  className="cursor-pointer border-b border-[var(--td-ink-600,#2b2b2b)]/60 bg-[var(--td-ink-900,#0d0d0d)] transition-colors hover:bg-[var(--td-brand-soft,#1c69d426)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--td-brand,#1c69d4)]"
                  style={{ boxShadow: `inset 3px 0 0 ${rail}` }}
                >
                  <td className="px-3 py-2 font-[family-name:var(--td-font-mono,ui-monospace,Menlo,monospace)] font-medium tabular-nums text-[var(--td-ink-100,#ffffff)]">
                    {row.symbol}
                  </td>
                  <td className="px-3 py-2">
                    <ActionChip action={row.action} />
                  </td>
                  <td className="px-3 py-2 text-right font-[family-name:var(--td-font-mono,ui-monospace,Menlo,monospace)] tabular-nums text-[var(--td-ink-200,#ffffff)]">
                    {formatNum(row.price, 2)}
                  </td>
                  <td className="px-3 py-2 text-right font-[family-name:var(--td-font-mono,ui-monospace,Menlo,monospace)] tabular-nums text-[var(--td-ink-200,#ffffff)]">
                    {formatPct(row.confidence, 0)}
                  </td>
                  <td className="px-3 py-2 text-right font-[family-name:var(--td-font-mono,ui-monospace,Menlo,monospace)] tabular-nums text-[var(--td-ink-200,#ffffff)]">
                    {formatPct(row.hitProbability, 0)}
                  </td>
                  <td className="px-3 py-2 text-right font-[family-name:var(--td-font-mono,ui-monospace,Menlo,monospace)] tabular-nums text-[var(--td-ink-200,#ffffff)]">
                    {formatNum(row.stop, 2)}
                  </td>
                  <td className="px-3 py-2 text-right font-[family-name:var(--td-font-mono,ui-monospace,Menlo,monospace)] tabular-nums text-[var(--td-ink-200,#ffffff)]">
                    {fmtRvol(row)}
                  </td>
                  <td className="max-w-[140px] truncate px-3 py-2 text-[var(--td-ink-300,#e6e6e6)]">
                    {row.model || "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-[var(--td-ink-600,#2b2b2b)] bg-[var(--td-ink-800,#1a1a1a)] px-3 py-2 text-[11px] text-[var(--td-ink-400,#bbbbbb)]">
        <span>
          last tick{" "}
          <span className="tabular-nums text-[var(--td-ink-300,#e6e6e6)]">
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
          <span className="text-[var(--td-brand,#1c69d4)]">refreshing</span>
        ) : null}
        {alerts.length > 0 ? (
          <span className="text-[var(--td-ink-300,#e6e6e6)]">
            alerts: {alerts.join(" · ")}
          </span>
        ) : null}
      </div>
    </div>
  );
}
