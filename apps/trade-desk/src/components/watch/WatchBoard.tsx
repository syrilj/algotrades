"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, ChevronDown, ChevronRight, Radio } from "lucide-react";
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
  /** Breakout trigger or entry zone */
  trigger?: number;
  entry?: number;
  breakoutLevel?: number;
  trailArm?: number;
  riskPerShare?: number;
  setupKind?: string;
  why?: string;
  doNext?: string;
  missing?: string[];
  shares?: number;
  dollarRisk?: number;
  score?: number;
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

/** Prefer explicit trigger (breakout level), else entry. */
function triggerOf(row: WatchBoardRow): number | undefined {
  if (row.trigger != null && Number.isFinite(row.trigger)) return row.trigger;
  if (row.breakoutLevel != null && Number.isFinite(row.breakoutLevel))
    return row.breakoutLevel;
  if (row.entry != null && Number.isFinite(row.entry)) return row.entry;
  return undefined;
}

/** Signed % from price → trigger. Negative = still below trigger (need rally). */
function distPct(row: WatchBoardRow): number | undefined {
  const t = triggerOf(row);
  if (t == null || !row.price || row.price <= 0) return undefined;
  return ((row.price - t) / t) * 100;
}

function distLabel(row: WatchBoardRow): string {
  const d = distPct(row);
  if (d == null) return "—";
  const sign = d > 0 ? "+" : "";
  return `${sign}${d.toFixed(2)}%`;
}

/** Compact operator line: what you are waiting on / what to do. */
function waitingOn(row: WatchBoardRow): string {
  if (row.doNext?.trim()) return row.doNext.trim();
  const a = (row.action || "").toUpperCase();
  const t = triggerOf(row);
  const tStr = t != null ? `$${t.toFixed(2)}` : "level";
  if (a.includes("BUY NOW")) {
    return `Enter near ${row.entry != null ? `$${row.entry.toFixed(2)}` : "spot"} · stop $${row.stop?.toFixed(2) ?? "—"}`;
  }
  if (a.includes("BUY BREAKOUT")) {
    return `Buy volume break of ${tStr} · stop $${row.stop?.toFixed(2) ?? "—"}`;
  }
  if (a.includes("BREAKOUT WATCH")) {
    return `No buy yet — alert above ${tStr} only with rvol surge (≥~1.3x)`;
  }
  if (a.includes("PULLBACK")) {
    return `Wait for dip toward entry/VAL · don't chase $${row.price.toFixed(2)}`;
  }
  if (a.includes("AVOID")) {
    return "Stand aside — structure / volume veto";
  }
  if (row.missing?.length) {
    return `Waiting on: ${row.missing.slice(0, 3).join(", ")}`;
  }
  return row.why?.trim() || "Conditions not aligned — monitor";
}

function actionRank(action: string): number {
  const a = action.toUpperCase();
  if (a.includes("BUY NOW")) return 0;
  if (a.includes("BUY BREAKOUT")) return 1;
  if (a.includes("BREAKOUT WATCH")) return 2;
  if (a.includes("PULLBACK")) return 3;
  if (a.includes("ALMOST")) return 4;
  if (a.includes("WAIT")) return 5;
  if (a.includes("AVOID")) return 6;
  return 7;
}

function mathLine(row: WatchBoardRow): string {
  const parts: string[] = [];
  if (row.confidence != null) parts.push(`conf ${formatPct(row.confidence, 0)}`);
  if (row.hitProbability != null) parts.push(`hit ${formatPct(row.hitProbability, 0)}`);
  if (row.stop != null) parts.push(`stop ${formatNum(row.stop, 2)}`);
  if (row.riskPerShare != null) parts.push(`R/sh ${formatNum(row.riskPerShare, 2)}`);
  if (row.shares != null && row.shares > 0) {
    parts.push(`${row.shares} sh`);
  }
  if (row.dollarRisk != null && row.dollarRisk > 0) {
    parts.push(`$${row.dollarRisk.toFixed(0)} risk`);
  }
  if (row.trailArm != null) parts.push(`trail ${formatNum(row.trailArm, 2)}`);
  return parts.join(" · ") || "—";
}

export function WatchBoard({
  rows,
  alerts = [],
  lastTick,
  loading = false,
  error = null,
  emptyHint = "Market scan for plays, or add symbols and press Start. Rows show action + what you're waiting on.",
  onSelectSymbol,
}: WatchBoardProps) {
  const router = useRouter();
  const [open, setOpen] = useState<string | null>(null);
  /** Default: hide pure AVOID so the board surfaces plays + levels first. */
  const [hideAvoid, setHideAvoid] = useState(true);

  const sorted = useMemo(() => {
    const filtered = hideAvoid
      ? rows.filter((r) => {
          const a = (r.action || "").toUpperCase();
          // Keep structural AVOID visible only when expanded filter is off.
          return !a.includes("AVOID");
        })
      : rows;
    return [...filtered].sort((a, b) => {
      const ra = actionRank(a.action);
      const rb = actionRank(b.action);
      if (ra !== rb) return ra - rb;
      const sa = a.score ?? a.hitProbability ?? a.confidence ?? 0;
      const sb = b.score ?? b.hitProbability ?? b.confidence ?? 0;
      return sb - sa;
    });
  }, [rows, hideAvoid]);

  const avoidCount = useMemo(
    () => rows.filter((r) => (r.action || "").toUpperCase().includes("AVOID")).length,
    [rows],
  );

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

  if (rows.length && !sorted.length && !loading) {
    return (
      <div className="flex flex-col gap-3">
        <EmptyState
          icon={Radio}
          title="Only AVOID rows"
          hint={`All ${avoidCount} symbols are AVOID (structure / red-flag). Uncheck Hide AVOID to inspect, or refresh when volume returns.`}
        />
        <label className="flex items-center gap-1.5 px-3 text-[12px] cursor-pointer" style={{ color: "var(--td-ink-300)" }}>
          <input
            type="checkbox"
            checked={hideAvoid}
            onChange={(e) => setHideAvoid(e.target.checked)}
          />
          Hide AVOID ({avoidCount})
        </label>
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[980px] border-collapse text-left text-[13px]">
          <thead className="sticky top-0 z-10 bg-[var(--td-surface-card)]">
            <tr className="border-b border-[var(--td-hairline)] text-[11px] font-medium uppercase tracking-wide text-[var(--td-muted)]">
              <th className="w-8 px-2 py-2" aria-label="expand" />
              <th className="px-3 py-2">Sym</th>
              <th className="px-3 py-2">Action</th>
              <th className="px-3 py-2 text-right">Price</th>
              <th className="px-3 py-2 text-right">Trigger</th>
              <th className="px-3 py-2 text-right">Dist</th>
              <th className="px-3 py-2">Do next / waiting on</th>
              <th className="px-3 py-2 text-right" title="Structure readiness (gates true)">
                Struct
              </th>
              <th className="px-3 py-2 text-right" title="Estimated hit probability">
                Hit%
              </th>
              <th className="px-3 py-2 text-right">RVOL</th>
              <th className="px-3 py-2">Model</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => {
              const rail = actionRailColor(row.action);
              const expanded = open === row.symbol;
              const trig = triggerOf(row);
              const dist = distPct(row);
              const distColor =
                dist == null
                  ? "var(--td-ink-300)"
                  : Math.abs(dist) <= 0.35
                    ? "var(--td-action-buy-breakout)"
                    : dist < 0
                      ? "var(--td-action-breakout-watch)"
                      : "var(--td-ink-200)";

              return (
                <FragmentRow
                  key={row.symbol}
                  row={row}
                  rail={rail}
                  expanded={expanded}
                  trig={trig}
                  distColor={distColor}
                  onToggle={() =>
                    setOpen((cur) => (cur === row.symbol ? null : row.symbol))
                  }
                  onSelect={() => select(row.symbol)}
                />
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
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={hideAvoid}
            onChange={(e) => setHideAvoid(e.target.checked)}
          />
          Hide AVOID
          {avoidCount > 0 ? (
            <span className="tabular-nums">({avoidCount})</span>
          ) : null}
        </label>
        <span>
          showing{" "}
          <span className="tabular-nums text-[var(--td-ink-300)]">{sorted.length}</span>
          /{rows.length}
        </span>
        {loading ? (
          <span className="text-[var(--td-brand,#1c69d4)]">refreshing</span>
        ) : null}
        <span style={{ color: "var(--td-ink-400)" }}>
          BREAKOUT WATCH = not a buy — wait for volume through trigger. Expand row for full math.
        </span>
        {alerts.length > 0 ? (
          <span className="text-[var(--td-ink-300,#e6e6e6)]">
            alerts: {alerts.join(" · ")}
          </span>
        ) : null}
      </div>
    </div>
  );
}

function FragmentRow({
  row,
  rail,
  expanded,
  trig,
  distColor,
  onToggle,
  onSelect,
}: {
  row: WatchBoardRow;
  rail: string;
  expanded: boolean;
  trig: number | undefined;
  distColor: string;
  onToggle: () => void;
  onSelect: () => void;
}) {
  return (
    <>
      <tr
        className="cursor-pointer border-b border-[var(--td-ink-600,#2b2b2b)]/60 bg-[var(--td-ink-900,#0d0d0d)] transition-colors hover:bg-[var(--td-brand-soft,#1c69d426)]"
        style={{ boxShadow: `inset 3px 0 0 ${rail}` }}
      >
        <td className="px-2 py-2">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onToggle();
            }}
            className="inline-flex size-6 items-center justify-center rounded text-[var(--td-ink-300)] hover:bg-[var(--td-ink-700)]"
            aria-label={expanded ? "Collapse" : "Expand operator detail"}
            aria-expanded={expanded}
          >
            {expanded ? (
              <ChevronDown className="size-3.5" strokeWidth={1.75} />
            ) : (
              <ChevronRight className="size-3.5" strokeWidth={1.75} />
            )}
          </button>
        </td>
        <td
          className="px-3 py-2 font-[family-name:var(--td-font-mono,ui-monospace,Menlo,monospace)] font-medium tabular-nums text-[var(--td-ink-100,#ffffff)]"
          onClick={onSelect}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              onSelect();
            }
          }}
          tabIndex={0}
          role="link"
        >
          {row.symbol}
        </td>
        <td className="px-3 py-2" onClick={onSelect}>
          <ActionChip action={row.action} size="sm" />
        </td>
        <td
          className="px-3 py-2 text-right font-[family-name:var(--td-font-mono,ui-monospace,Menlo,monospace)] tabular-nums text-[var(--td-ink-200,#ffffff)]"
          onClick={onSelect}
        >
          {formatNum(row.price, 2)}
        </td>
        <td
          className="px-3 py-2 text-right font-[family-name:var(--td-font-mono,ui-monospace,Menlo,monospace)] tabular-nums text-[var(--td-ink-200,#ffffff)]"
          onClick={onSelect}
          title={
            row.setupKind === "breakout_watch" || row.breakoutLevel != null
              ? "Breakout level — enter only with volume"
              : row.entry != null
                ? "Entry zone"
                : undefined
          }
        >
          {trig != null ? formatNum(trig, 2) : "—"}
        </td>
        <td
          className="px-3 py-2 text-right font-[family-name:var(--td-font-mono,ui-monospace,Menlo,monospace)] tabular-nums"
          style={{ color: distColor }}
          onClick={onSelect}
          title="Price vs trigger (negative = still needs to rally into break)"
        >
          {distLabel(row)}
        </td>
        <td
          className="max-w-[320px] px-3 py-2 text-[12px] leading-snug text-[var(--td-ink-200,#ffffff)]"
          onClick={onSelect}
          title={waitingOn(row)}
        >
          <span className="line-clamp-2">{waitingOn(row)}</span>
        </td>
        <td
          className="px-3 py-2 text-right font-[family-name:var(--td-font-mono,ui-monospace,Menlo,monospace)] tabular-nums text-[var(--td-ink-200,#ffffff)]"
          onClick={onSelect}
        >
          {formatPct(row.confidence, 0)}
        </td>
        <td
          className="px-3 py-2 text-right font-[family-name:var(--td-font-mono,ui-monospace,Menlo,monospace)] tabular-nums text-[var(--td-ink-200,#ffffff)]"
          onClick={onSelect}
        >
          {formatPct(row.hitProbability, 0)}
        </td>
        <td
          className="px-3 py-2 text-right font-[family-name:var(--td-font-mono,ui-monospace,Menlo,monospace)] tabular-nums text-[var(--td-ink-200,#ffffff)]"
          onClick={onSelect}
        >
          {fmtRvol(row)}
        </td>
        <td
          className="max-w-[120px] truncate px-3 py-2 text-[var(--td-ink-300,#e6e6e6)]"
          onClick={onSelect}
          title={row.model}
        >
          {row.model || "—"}
        </td>
      </tr>
      {expanded ? (
        <tr
          className="border-b border-[var(--td-ink-600,#2b2b2b)]/60"
          style={{
            boxShadow: `inset 3px 0 0 ${rail}`,
            background: "var(--td-surface-soft, #141414)",
          }}
        >
          <td colSpan={11} className="px-4 py-3">
            <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
              <div>
                <div
                  className="mb-1 text-[10px] font-medium uppercase tracking-wide"
                  style={{ color: "var(--td-ink-400)" }}
                >
                  Why
                </div>
                <p className="text-[12px] leading-relaxed" style={{ color: "var(--td-ink-200)" }}>
                  {row.why || "—"}
                </p>
              </div>
              <div>
                <div
                  className="mb-1 text-[10px] font-medium uppercase tracking-wide"
                  style={{ color: "var(--td-ink-400)" }}
                >
                  Do next
                </div>
                <p className="text-[12px] leading-relaxed" style={{ color: "var(--td-ink-100)" }}>
                  {waitingOn(row)}
                </p>
                {row.missing && row.missing.length > 0 ? (
                  <p
                    className="mt-1.5 text-[11px]"
                    style={{ color: "var(--td-action-breakout-watch)" }}
                  >
                    Gates still open: {row.missing.join(", ")}
                  </p>
                ) : (
                  <p
                    className="mt-1.5 text-[11px]"
                    style={{ color: "var(--td-ink-400)" }}
                  >
                    setup: {row.setupKind || "—"}
                  </p>
                )}
              </div>
              <div className="min-w-[200px]">
                <div
                  className="mb-1 text-[10px] font-medium uppercase tracking-wide"
                  style={{ color: "var(--td-ink-400)" }}
                >
                  Evaluation math
                </div>
                <p
                  className="font-[family-name:var(--td-font-mono,ui-monospace,Menlo,monospace)] text-[12px] tabular-nums leading-relaxed"
                  style={{ color: "var(--td-ink-200)" }}
                >
                  {mathLine(row)}
                </p>
                <button
                  type="button"
                  className="td-btn td-btn-ghost mt-2 text-[11px]"
                  onClick={onSelect}
                >
                  Full analyze →
                </button>
              </div>
            </div>
          </td>
        </tr>
      ) : null}
    </>
  );
}
