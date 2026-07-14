"use client";

import { useMemo, useState } from "react";
import { Circle } from "lucide-react";
import { ModelBadges } from "./ModelBadges";
import { ScoreBar } from "./ScoreBar";
import type { LeaderboardRow } from "./ModelSidePanel";
import { rankColorVar } from "@/lib/actionColors";

export type SortKey =
  | "rank"
  | "model"
  | "score"
  | "win_rate"
  | "sharpe"
  | "profit_factor"
  | "max_drawdown"
  | "total_return"
  | "trade_count";

type LeaderboardTableProps = {
  rows: LeaderboardRow[];
  selectedModel?: string | null;
  onSelect?: (row: LeaderboardRow) => void;
  sortKey?: SortKey;
  sortDir?: "asc" | "desc";
  onSortChange?: (key: SortKey, dir: "asc" | "desc") => void;
};

const COLUMNS: { key: SortKey; label: string; align?: "left" | "right" }[] = [
  { key: "rank", label: "#" },
  { key: "model", label: "Model", align: "left" },
  { key: "score", label: "Score", align: "left" },
  { key: "win_rate", label: "WR" },
  { key: "sharpe", label: "Sharpe" },
  { key: "profit_factor", label: "PF" },
  { key: "max_drawdown", label: "DD" },
  { key: "total_return", label: "Ret" },
  { key: "trade_count", label: "Trades" },
];

function fmtPct(n: number | undefined, digits = 1): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}

function fmtNum(n: number | undefined, digits = 2): string {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toFixed(digits);
}

function cellValue(row: LeaderboardRow, key: SortKey): number | string {
  switch (key) {
    case "rank":
      return row.rank;
    case "model":
      return row.model;
    case "score":
      return row.score;
    case "win_rate":
      return row.win_rate ?? Number.NEGATIVE_INFINITY;
    case "sharpe":
      return row.sharpe ?? Number.NEGATIVE_INFINITY;
    case "profit_factor":
      return row.profit_factor ?? Number.NEGATIVE_INFINITY;
    case "max_drawdown":
      return row.max_drawdown ?? Number.POSITIVE_INFINITY;
    case "total_return":
      return row.total_return ?? Number.NEGATIVE_INFINITY;
    case "trade_count":
      return row.trade_count ?? Number.NEGATIVE_INFINITY;
    default: {
      const _exhaustive: never = key;
      return _exhaustive;
    }
  }
}

export function LeaderboardTable({
  rows,
  selectedModel,
  onSelect,
  sortKey: controlledKey,
  sortDir: controlledDir,
  onSortChange,
}: LeaderboardTableProps) {
  const [localKey, setLocalKey] = useState<SortKey>("score");
  const [localDir, setLocalDir] = useState<"asc" | "desc">("desc");
  const sortKey = controlledKey ?? localKey;
  const sortDir = controlledDir ?? localDir;

  const maxScore = useMemo(
    () => Math.max(1, ...rows.map((r) => r.score || 0)),
    [rows],
  );

  const sorted = useMemo(() => {
    const copy = [...rows];
    copy.sort((a, b) => {
      const av = cellValue(a, sortKey);
      const bv = cellValue(b, sortKey);
      let cmp = 0;
      if (typeof av === "string" && typeof bv === "string") {
        cmp = av.localeCompare(bv);
      } else {
        cmp = Number(av) - Number(bv);
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
    return copy;
  }, [rows, sortKey, sortDir]);

  function toggleSort(key: SortKey) {
    const nextDir =
      sortKey === key
        ? sortDir === "asc"
          ? "desc"
          : "asc"
        : key === "max_drawdown"
          ? "asc"
          : "desc";
    if (onSortChange) onSortChange(key, nextDir);
    else {
      setLocalKey(key);
      setLocalDir(nextDir);
    }
  }

  if (!rows.length) {
    return (
      <div
        className="p-8 text-center text-[13px]"
        style={{ color: "var(--td-ink-400, #bbbbbb)" }}
      >
        No ranked models for this view.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr
            style={{
              borderBottom: "1px solid var(--td-ink-700, #3c3c3c)",
              color: "var(--td-ink-400, #bbbbbb)",
            }}
          >
            {COLUMNS.map((col) => (
              <th
                key={col.key}
                scope="col"
                className={`py-2 px-2 font-medium ${
                  col.align === "left" ? "text-left" : "text-right"
                }`}
              >
                <button
                  type="button"
                  onClick={() => toggleSort(col.key)}
                  className="inline-flex items-center gap-1 hover:opacity-80"
                  aria-label={`Sort by ${col.label}`}
                >
                  {col.label}
                  {sortKey === col.key ? (
                    <span aria-hidden>{sortDir === "asc" ? "↑" : "↓"}</span>
                  ) : null}
                </button>
              </th>
            ))}
            <th scope="col" className="py-2 px-2 text-left font-medium">
              Badges
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => {
            const selected = selectedModel === row.model;
            return (
              <tr
                key={row.model}
                onClick={() => onSelect?.(row)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onSelect?.(row);
                  }
                }}
                tabIndex={0}
                role="button"
                aria-pressed={selected}
                className="cursor-pointer transition-colors"
                style={{
                  borderBottom: "1px solid var(--td-ink-800, #1a1a1a)",
                  background: selected
                    ? "var(--td-brand-soft, #1c69d426)"
                    : row.isWinner
                      ? "var(--td-brand-soft, #1c69d414)"
                      : "transparent",
                  boxShadow: row.isWinner
                    ? "inset 2px 0 0 var(--td-brand, #1c69d4)"
                    : undefined,
                  color: "var(--td-ink-200, #ffffff)",
                }}
              >
                <td className="py-2.5 px-2 text-right tabular-nums">
                  <span
                    className="inline-flex items-center justify-center gap-0.5 min-w-[1.5rem] font-medium"
                    style={{
                      color: rankColorVar(row.rank),
                      fontFamily:
                        "var(--td-font-mono, ui-monospace, Menlo, monospace)",
                    }}
                    aria-label={`Rank ${row.rank}`}
                  >
                    {row.rank <= 3 ? (
                      <Circle size={8} fill="currentColor" aria-hidden />
                    ) : (
                      "#"
                    )}
                    {row.rank}
                  </span>
                </td>
                <td
                  className="py-2.5 px-2 text-left"
                  style={{
                    fontFamily:
                      "var(--td-font-mono, ui-monospace, Menlo, monospace)",
                    color: "var(--td-ink-100, #ffffff)",
                  }}
                >
                  {row.model}
                </td>
                <td className="py-2.5 px-2">
                  <ScoreBar
                    value={row.score}
                    max={maxScore}
                    winner={row.isWinner}
                  />
                </td>
                <td
                  className="py-2.5 px-2 text-right tabular-nums"
                  style={{
                    fontFamily:
                      "var(--td-font-mono, ui-monospace, Menlo, monospace)",
                  }}
                >
                  {fmtPct(row.win_rate)}
                </td>
                <td
                  className="py-2.5 px-2 text-right tabular-nums"
                  style={{
                    fontFamily:
                      "var(--td-font-mono, ui-monospace, Menlo, monospace)",
                  }}
                >
                  {fmtNum(row.sharpe)}
                </td>
                <td
                  className="py-2.5 px-2 text-right tabular-nums"
                  style={{
                    fontFamily:
                      "var(--td-font-mono, ui-monospace, Menlo, monospace)",
                  }}
                >
                  {fmtNum(row.profit_factor)}
                </td>
                <td
                  className="py-2.5 px-2 text-right tabular-nums"
                  style={{
                    fontFamily:
                      "var(--td-font-mono, ui-monospace, Menlo, monospace)",
                  }}
                >
                  {fmtPct(row.max_drawdown)}
                </td>
                <td
                  className="py-2.5 px-2 text-right tabular-nums"
                  style={{
                    fontFamily:
                      "var(--td-font-mono, ui-monospace, Menlo, monospace)",
                  }}
                >
                  {fmtPct(row.total_return)}
                </td>
                <td
                  className="py-2.5 px-2 text-right tabular-nums"
                  style={{
                    fontFamily:
                      "var(--td-font-mono, ui-monospace, Menlo, monospace)",
                  }}
                >
                  {row.trade_count != null ? row.trade_count : "—"}
                </td>
                <td className="py-2.5 px-2">
                  <ModelBadges
                    isWinner={row.isWinner}
                    isDefault={row.isDefault}
                    hasEngine={row.has_engine}
                    status={row.status}
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
