"use client";

import Link from "next/link";
import { useState } from "react";

import { formatNum, formatUsd } from "@/lib/format";
import { analyzeHref, modelHref } from "@/lib/routes";
import type { LedgerStatsRow, PaperPosition } from "@/lib/types";

type PositionsTableProps = {
  positions: PaperPosition[];
  statsRows: LedgerStatsRow[];
  onClose: (id: string, exit: number) => Promise<void>;
  closingId?: string | null;
};

function pnlColor(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n) || n === 0) return "var(--td-ink-200)";
  return n > 0 ? "var(--td-action-buy-now)" : "var(--td-action-avoid)";
}

function OpenRow({
  row,
  onClose,
  closing,
}: {
  row: PaperPosition;
  onClose: (id: string, exit: number) => Promise<void>;
  closing: boolean;
}) {
  const [showClose, setShowClose] = useState(false);
  const [exit, setExit] = useState(String(row.mark ?? row.entry ?? ""));

  return (
    <tr>
      <td>
        <Link href={analyzeHref({ symbol: row.symbol })} className="no-underline">
          {row.symbol}
        </Link>
      </td>
      <td>{row.side}</td>
      <td>
        <Link href={modelHref(row.model)} className="no-underline">
          {row.model}
        </Link>
      </td>
      <td className="tabular">{row.shares}</td>
      <td className="tabular">{formatNum(row.entry)}</td>
      <td className="tabular">{formatNum(row.stop)}</td>
      <td className="tabular">{formatNum(row.mark)}</td>
      <td className="tabular" style={{ color: pnlColor(row.unrealized_pnl) }}>
        {formatUsd(row.unrealized_pnl)}
      </td>
      <td className="tabular">{formatNum(row.unrealized_r, 2)}R</td>
      <td className="tabular text-[11px]">{row.opened_at?.slice(0, 10) ?? "—"}</td>
      <td>
        {row.stop_hit ? (
          <span className="td-chip text-[10px]" style={{ color: "var(--td-action-avoid)" }}>
            STOP HIT
          </span>
        ) : null}
      </td>
      <td>
        {showClose ? (
          <div className="flex items-center gap-1">
            <input
              className="td-input w-20 tabular text-[11px]"
              value={exit}
              onChange={(e) => setExit(e.target.value)}
            />
            <button
              type="button"
              className="td-btn td-btn-ghost text-[11px]"
              disabled={closing}
              onClick={() => void onClose(row.id, Number(exit)).then(() => setShowClose(false))}
            >
              OK
            </button>
          </div>
        ) : (
          <button
            type="button"
            className="td-btn td-btn-ghost text-[11px]"
            onClick={() => setShowClose(true)}
          >
            Close
          </button>
        )}
      </td>
    </tr>
  );
}

export function PositionsTable({
  positions,
  statsRows,
  onClose,
  closingId,
}: PositionsTableProps) {
  const open = positions.filter((p) => p.status === "open");
  const closed = positions.filter((p) => p.status === "closed");

  if (positions.length === 0) {
    return (
      <p className="text-[13px]" style={{ color: "var(--td-ink-300)" }}>
        No paper trades yet — log one from Analyze → Verdict → Log paper trade.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {open.length > 0 ? (
        <div className="overflow-x-auto">
          <span className="td-label">Open</span>
          <table className="mt-2 w-full text-[12px]" style={{ fontFamily: "var(--td-font-mono)" }}>
            <thead>
              <tr style={{ color: "var(--td-ink-400)" }}>
                <th className="text-left py-1">SYM</th>
                <th className="text-left py-1">Side</th>
                <th className="text-left py-1">Model</th>
                <th className="text-right py-1">Sh</th>
                <th className="text-right py-1">Entry</th>
                <th className="text-right py-1">Stop</th>
                <th className="text-right py-1">Mark</th>
                <th className="text-right py-1">Unreal $</th>
                <th className="text-right py-1">Unreal R</th>
                <th className="text-left py-1">Opened</th>
                <th className="text-left py-1">Flags</th>
                <th className="text-left py-1" />
              </tr>
            </thead>
            <tbody>
              {open.map((row) => (
                <OpenRow
                  key={row.id}
                  row={row}
                  onClose={onClose}
                  closing={closingId === row.id}
                />
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {closed.length > 0 ? (
        <div className="overflow-x-auto">
          <span className="td-label">Closed</span>
          <table className="mt-2 w-full text-[12px]" style={{ fontFamily: "var(--td-font-mono)" }}>
            <thead>
              <tr style={{ color: "var(--td-ink-400)" }}>
                <th className="text-left py-1">SYM</th>
                <th className="text-left py-1">Model</th>
                <th className="text-right py-1">Exit</th>
                <th className="text-right py-1">PnL</th>
                <th className="text-right py-1">R</th>
                <th className="text-left py-1">Reason</th>
                <th className="text-left py-1">Closed</th>
              </tr>
            </thead>
            <tbody>
              {closed.map((row) => (
                <tr key={row.id}>
                  <td>{row.symbol}</td>
                  <td>{row.model}</td>
                  <td className="tabular text-right">{formatNum(row.exit)}</td>
                  <td className="tabular text-right" style={{ color: pnlColor(row.pnl) }}>
                    {formatUsd(row.pnl)}
                  </td>
                  <td className="tabular text-right">{formatNum(row.r_multiple, 2)}R</td>
                  <td>{row.exit_reason ?? "—"}</td>
                  <td className="text-[11px]">{row.closed_at?.slice(0, 10) ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {statsRows.length > 0 ? (
        <div
          className="border-t pt-3 text-[11px]"
          style={{ borderColor: "var(--td-ink-700)", color: "var(--td-ink-300)" }}
        >
          <span className="td-label">Live model stats</span>
          <ul className="mt-2 flex flex-col gap-1">
            {statsRows.map((s) => (
              <li key={`${s.model}-${s.symbol}`} className="tabular">
                {s.model} · {s.symbol} · {s.n} trades · WR {(s.live_wr * 100).toFixed(0)}% ·{" "}
                {s.total_pnl >= 0 ? "+" : ""}
                {formatUsd(s.total_pnl, 0)} · {formatNum(s.avg_R, 2)}R
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
