"use client";

import Link from "next/link";
import type { ModelRankRow } from "@/lib/types";
import { analyzeHref, modelHref } from "@/lib/routes";
import { ModelBadges } from "./ModelBadges";
import { ScoreBar } from "./ScoreBar";

export type LeaderboardRow = ModelRankRow & {
  isWinner?: boolean;
  isDefault?: boolean;
  status?: string | null;
};

type ModelSidePanelProps = {
  row: LeaderboardRow | null;
  maxScore?: number;
  onClose?: () => void;
};

function fmtPct(n: number | undefined, digits = 1): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}

function fmtNum(n: number | undefined, digits = 2): string {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toFixed(digits);
}

export function ModelSidePanel({ row, maxScore = 1, onClose }: ModelSidePanelProps) {
  if (!row) {
    return (
      <aside
        className="p-4 text-[13px]"
        style={{
          background: "var(--td-ink-900, #0d0d0d)",
          borderLeft: "1px solid var(--td-ink-700, #3c3c3c)",
          color: "var(--td-ink-400, #bbbbbb)",
          minHeight: "12rem",
        }}
        aria-label="Model detail panel"
      >
        Select a row to inspect metrics and open Analyze.
      </aside>
    );
  }

  const withModelHref = analyzeHref({ model: row.model });
  const detailHref = modelHref(row.model);

  return (
    <aside
      className="flex flex-col gap-4 p-4"
      style={{
        background: "var(--td-ink-900, #0d0d0d)",
        borderLeft: "1px solid var(--td-ink-700, #3c3c3c)",
        color: "var(--td-ink-200, #ffffff)",
      }}
      aria-label={`Detail for ${row.model}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p
            className="text-[11px] uppercase tracking-wide"
            style={{ color: "var(--td-ink-400, #bbbbbb)" }}
          >
            Rank #{row.rank}
          </p>
          <h2
            className="text-[16px] font-medium mt-0.5"
            style={{
              fontFamily: "var(--td-font-mono, ui-monospace, Menlo, monospace)",
              color: "var(--td-ink-100, #ffffff)",
            }}
          >
            {row.model}
          </h2>
        </div>
        {onClose ? (
          <button
            type="button"
            onClick={onClose}
            className="text-[12px] px-2 py-1 rounded-sm"
            style={{
              color: "var(--td-ink-400, #bbbbbb)",
              border: "1px solid var(--td-ink-700, #3c3c3c)",
            }}
            aria-label="Close panel"
          >
            Close
          </button>
        ) : null}
      </div>

      <ModelBadges
        isWinner={row.isWinner}
        isDefault={row.isDefault}
        hasEngine={row.has_engine}
        status={row.status}
      />

      <div>
        <p
          className="text-[12px] mb-1"
          style={{ color: "var(--td-ink-400, #bbbbbb)" }}
        >
          Score
        </p>
        <ScoreBar value={row.score} max={maxScore} winner={row.isWinner} />
      </div>

      <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-[13px]">
        {(
          [
            ["WR", fmtPct(row.win_rate)],
            ["Sharpe", fmtNum(row.sharpe)],
            ["PF", fmtNum(row.profit_factor)],
            ["DD", fmtPct(row.max_drawdown)],
            ["Ret", fmtPct(row.total_return)],
            ["Trades", row.trade_count != null ? String(row.trade_count) : "—"],
          ] as const
        ).map(([label, value]) => (
          <div key={label}>
            <dt style={{ color: "var(--td-ink-400, #bbbbbb)", fontSize: 11 }}>
              {label}
            </dt>
            <dd
              className="tabular-nums"
              style={{
                fontFamily: "var(--td-font-mono, ui-monospace, Menlo, monospace)",
              }}
            >
              {value}
            </dd>
          </div>
        ))}
      </dl>

      {row.specialist || row.code || row.source ? (
        <div
          className="text-[12px] space-y-1 pt-2"
          style={{
            borderTop: "1px solid var(--td-ink-700, #3c3c3c)",
            color: "var(--td-ink-300, #e6e6e6)",
          }}
        >
          {row.code ? <p>Code: {row.code}</p> : null}
          {row.specialist ? <p>Specialist: {row.specialist}</p> : null}
          {row.source ? <p>Source: {row.source}</p> : null}
        </div>
      ) : null}

      <div className="flex flex-col gap-2 mt-auto pt-2">
        <Link
          href={detailHref}
          className="text-center text-[13px] py-2 rounded-sm transition-colors"
          style={{
            background: "var(--td-canvas)",
            border: "1px solid var(--td-ink)",
            color: "var(--td-ink)",
          }}
        >
          Model detail
        </Link>
        <Link
          href={withModelHref}
          className="text-center text-[13px] py-2 rounded-sm transition-colors"
          style={{
            background: "transparent",
            border: "1px solid var(--td-ink)",
            color: "var(--td-ink)",
          }}
        >
          Analyze with model
        </Link>
      </div>
    </aside>
  );
}
