"use client";

import Link from "next/link";
import type { ModelRankRow } from "@/lib/types";

type TopModelsStripProps = {
  symbol: string;
  ranks?: ModelRankRow[] | null;
  topN?: number;
  onUseAuto?: () => void;
};

function fmtPct(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(0)}%`;
}

function fmtSharpe(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return n.toFixed(2);
}

export function TopModelsStrip({
  symbol,
  ranks,
  topN = 5,
  onUseAuto,
}: TopModelsStripProps) {
  const list = (ranks ?? []).slice(0, topN);
  const leaderboardHref = `/leaderboard?symbol=${encodeURIComponent(symbol)}`;

  if (!symbol) return null;

  return (
    <section
      className="flex flex-wrap items-center gap-3 border-t py-3"
      style={{ borderColor: "var(--td-ink-700)" }}
      aria-label={`Best models for ${symbol}`}
    >
      <span
        className="text-[12px] font-medium"
        style={{ color: "var(--td-ink-300)" }}
      >
        Best models for{" "}
        <span
          style={{ color: "var(--td-ink-100)", fontFamily: "var(--td-font-mono)" }}
        >
          {symbol}
        </span>
      </span>

      {list.length === 0 ? (
        <span className="text-[11px]" style={{ color: "var(--td-ink-500)" }}>
          No symbol ranks yet
        </span>
      ) : (
        <ul className="flex flex-wrap items-center gap-2">
          {list.map((row) => (
            <li
              key={`${row.rank}-${row.model}`}
              className="inline-flex items-center gap-1.5 px-2 py-1 text-[11px]"
              style={{
                border: "1px solid var(--td-ink-600)",
                borderRadius: "var(--td-radius-sm)",
                background: "var(--td-ink-900)",
              }}
            >
              <span style={{ color: "var(--td-rank-gold)" }}>#{row.rank}</span>
              <Link
                href={`/models/${encodeURIComponent(row.model)}`}
                className="no-underline"
                style={{
                  fontFamily: "var(--td-font-mono)",
                  color: "var(--td-ink-100)",
                }}
              >
                {row.model}
              </Link>
              <span
                className="tabular"
                style={{
                  fontFamily: "var(--td-font-mono)",
                  color: "var(--td-ink-400)",
                }}
              >
                WR {fmtPct(row.win_rate)} · Sh {fmtSharpe(row.sharpe)}
              </span>
            </li>
          ))}
        </ul>
      )}

      <div className="ml-auto flex items-center gap-2">
        <Link href={leaderboardHref} className="td-btn td-btn-ghost no-underline">
          Leaderboard →
        </Link>
        {onUseAuto ? (
          <button type="button" className="td-btn td-btn-ghost" onClick={onUseAuto}>
            Use auto
          </button>
        ) : null}
      </div>
    </section>
  );
}
