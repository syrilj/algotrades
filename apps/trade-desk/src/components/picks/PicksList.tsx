"use client";

import { useRouter } from "next/navigation";
import { AlertTriangle, ListFilter } from "lucide-react";
import { ActionChip, actionRailColor } from "@/components/ui/ActionChip";
import { EmptyState } from "@/components/ui/EmptyState";
import { analyzeHref } from "@/lib/routes";
import { formatPct, formatUsd } from "@/lib/format";

export type PickRow = {
  symbol: string;
  action: string;
  setupKind?: string;
  price?: number;
  confidence?: number;
  dollarRisk?: number;
  doNext?: string;
  model?: string;
};

type PicksListProps = {
  rows: PickRow[];
  loading?: boolean;
  error?: string | null;
  emptyHint?: string;
  onSelectSymbol?: (sym: string) => void;
};

const GROUP_ORDER = [
  "BUY NOW",
  "BUY BREAKOUT",
  "BREAKOUT WATCH",
  "PULLBACK ZONE",
  "WAIT",
  "WAIT (almost ready)",
  "WAIT / AVOID",
  "AVOID",
  "AVOID (structure broken)",
] as const;

function groupKey(action: string): string {
  const a = action || "WAIT";
  if (a.startsWith("BUY NOW")) return "BUY NOW";
  if (a.startsWith("BUY BREAKOUT")) return "BUY BREAKOUT";
  if (a.startsWith("BREAKOUT WATCH")) return "BREAKOUT WATCH";
  if (a.startsWith("PULLBACK")) return "PULLBACK ZONE";
  if (a.startsWith("AVOID")) {
    return a.includes("structure") ? "AVOID (structure broken)" : "AVOID";
  }
  if (a.includes("almost")) return "WAIT (almost ready)";
  if (a.includes("WAIT / AVOID")) return "WAIT / AVOID";
  if (a.startsWith("WAIT")) return "WAIT";
  return a;
}

function groupTitle(key: string): string {
  if (key === "BUY NOW" || key === "BUY BREAKOUT") {
    return "BUY NOW / BUY BREAKOUT";
  }
  if (
    key === "WAIT" ||
    key === "WAIT (almost ready)" ||
    key === "WAIT / AVOID"
  ) {
    return "OTHER HIGH-CONF WAIT";
  }
  return key;
}

export function PicksList({
  rows,
  loading = false,
  error = null,
  emptyHint = "Choose horizon and sectors, then Scan.",
  onSelectSymbol,
}: PicksListProps) {
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
          <div className="font-medium">Picks failed</div>
          <div style={{ color: "var(--td-ink-300)" }}>{error}</div>
        </div>
      </div>
    );
  }

  if (!rows.length && !loading) {
    return <EmptyState icon={ListFilter} title="No picks" hint={emptyHint} />;
  }

  const buckets = new Map<string, PickRow[]>();
  for (const row of rows) {
    const key = groupKey(row.action);
    const list = buckets.get(key) ?? [];
    list.push(row);
    buckets.set(key, list);
  }

  const orderedKeys = [
    ...GROUP_ORDER.filter((k) => buckets.has(k)),
    ...[...buckets.keys()].filter(
      (k) => !(GROUP_ORDER as readonly string[]).includes(k),
    ),
  ];

  const mergedTitles = new Map<string, PickRow[]>();
  for (const key of orderedKeys) {
    const title = groupTitle(key);
    const existing = mergedTitles.get(title) ?? [];
    mergedTitles.set(title, [...existing, ...(buckets.get(key) ?? [])]);
  }

  const displayTitles = [
    "BUY NOW / BUY BREAKOUT",
    "BREAKOUT WATCH",
    "PULLBACK ZONE",
    "OTHER HIGH-CONF WAIT",
    "AVOID",
    "AVOID (structure broken)",
  ];

  const extras = [...mergedTitles.keys()].filter(
    (t) => !displayTitles.includes(t),
  );

  return (
    <div className="flex flex-col gap-4 p-3">
      {loading && !rows.length ? (
        <p className="text-[13px] text-[var(--td-ink-400,#bbbbbb)]">Scanning…</p>
      ) : null}

      {[...displayTitles, ...extras].map((title) => {
        const list = mergedTitles.get(title) ?? [];
        const showEmptyShell = displayTitles.includes(title);
        if (!list.length && !showEmptyShell) return null;
        if (!list.length && rows.length === 0) return null;

        return (
          <section key={title} className="flex flex-col gap-1.5">
            <h2 className="text-[12px] font-semibold uppercase tracking-wide text-[var(--td-ink-300,#e6e6e6)]">
              {title}
            </h2>
            {list.length === 0 ? (
              <p className="px-1 text-[12px] text-[var(--td-ink-500,#7e7e7e)]">
                None live
              </p>
            ) : (
              <ul className="flex flex-col gap-1">
                {list.map((row) => (
                  <li key={`${title}-${row.symbol}-${row.action}`}>
                    <button
                      type="button"
                      onClick={() => select(row.symbol)}
                      className="flex w-full items-center gap-3 rounded-sm border border-transparent bg-[var(--td-ink-900,#0d0d0d)] px-3 py-2 text-left transition-colors hover:border-[var(--td-ink-600,#2b2b2b)] hover:bg-[var(--td-brand-soft,#1c69d426)]"
                      style={{
                        boxShadow: `inset 3px 0 0 ${actionRailColor(row.action)}`,
                      }}
                    >
                      <span className="w-14 shrink-0 font-[family-name:var(--td-font-mono,ui-monospace,Menlo,monospace)] font-medium tabular-nums text-[var(--td-ink-100,#ffffff)]">
                        {row.symbol}
                      </span>
                      <ActionChip action={row.action} />
                      {row.setupKind ? (
                        <span className="hidden text-[11px] uppercase text-[var(--td-ink-400,#bbbbbb)] sm:inline">
                          {row.setupKind}
                        </span>
                      ) : null}
                      <span className="ml-auto flex flex-wrap items-center gap-x-3 gap-y-0.5 font-[family-name:var(--td-font-mono,ui-monospace,Menlo,monospace)] text-[12px] tabular-nums text-[var(--td-ink-300,#e6e6e6)]">
                        <span>{formatUsd(row.price)}</span>
                        <span>conf {formatPct(row.confidence, 0)}</span>
                        {row.dollarRisk != null ? (
                          <span>risk ${Math.round(row.dollarRisk)}</span>
                        ) : null}
                      </span>
                      {row.doNext ? (
                        <span className="hidden max-w-[220px] truncate text-[12px] text-[var(--td-ink-400,#bbbbbb)] lg:inline">
                          → {row.doNext}
                        </span>
                      ) : null}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
}
