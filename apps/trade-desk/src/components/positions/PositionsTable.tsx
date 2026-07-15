"use client";

import Link from "next/link";
import { useState } from "react";

import { formatNum, formatUsd } from "@/lib/format";
import { analyzeHref, liveHref, modelHref } from "@/lib/routes";
import type { LedgerStatsRow, PaperPosition } from "@/lib/types";

export type PositionsTableMode = "open" | "history" | "all";

type PositionsTableProps = {
  positions: PaperPosition[];
  statsRows: LedgerStatsRow[];
  onClose: (id: string, exit: number) => Promise<void>;
  onUpdate?: (id: string, updates: { shares?: number; entry?: number; stop?: number }) => Promise<void>;
  onDelete?: (id: string) => Promise<void>;
  closingId?: string | null;
  /** open = live risk only; history = closed + model stats; all = both (legacy). */
  mode?: PositionsTableMode;
};

function pnlColor(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n) || n === 0) return "var(--td-ink-200)";
  return n > 0 ? "var(--td-action-buy-now)" : "var(--td-action-avoid)";
}

function OpenRow({
  row,
  onClose,
  onUpdate,
  onDelete,
  closing,
}: {
  row: PaperPosition;
  onClose: (id: string, exit: number) => Promise<void>;
  onUpdate?: (id: string, updates: { shares?: number; entry?: number; stop?: number }) => Promise<void>;
  onDelete?: (id: string) => Promise<void>;
  closing: boolean;
}) {
  const [showClose, setShowClose] = useState(false);
  const [exit, setExit] = useState(String(row.mark ?? row.entry ?? ""));

  const [isEditing, setIsEditing] = useState(false);
  const [editShares, setEditShares] = useState(String(row.shares));
  const [editEntry, setEditEntry] = useState(String(row.entry));
  const [editStop, setEditStop] = useState(String(row.stop));
  const [updating, setUpdating] = useState(false);

  const saveEdit = async () => {
    if (!onUpdate) return;
    setUpdating(true);
    try {
      await onUpdate(row.id, {
        shares: Number(editShares),
        entry: Number(editEntry),
        stop: Number(editStop),
      });
      setIsEditing(false);
    } catch {
      // handled by page state
    } finally {
      setUpdating(false);
    }
  };

  const deleteRow = async () => {
    if (!onDelete) return;
    if (confirm(`Are you sure you want to delete ${row.symbol} trade ${row.id}?`)) {
      setUpdating(true);
      try {
        await onDelete(row.id);
      } catch {
        // handled
      } finally {
        setUpdating(false);
      }
    }
  };

  if (isEditing) {
    return (
      <tr>
        <td>
          <div className="flex flex-col gap-0.5">
            <Link href={liveHref(row.symbol)} className="no-underline font-semibold">
              {row.symbol}
            </Link>
            <Link
              href={analyzeHref({ symbol: row.symbol })}
              className="no-underline text-[10px]"
              style={{ color: "var(--td-ink-400)" }}
            >
              Analyze
            </Link>
          </div>
        </td>
        <td>{row.side}</td>
        <td>
          <Link href={modelHref(row.model)} className="no-underline">
            {row.model}
          </Link>
        </td>
        <td>
          <input
            className="td-input w-16 tabular text-[11px]"
            value={editShares}
            onChange={(e) => setEditShares(e.target.value)}
          />
        </td>
        <td>
          <input
            className="td-input w-20 tabular text-[11px]"
            value={editEntry}
            onChange={(e) => setEditEntry(e.target.value)}
          />
        </td>
        <td>
          <input
            className="td-input w-20 tabular text-[11px]"
            value={editStop}
            onChange={(e) => setEditStop(e.target.value)}
          />
        </td>
        <td className="tabular">{formatNum(row.mark)}</td>
        <td className="tabular" style={{ color: pnlColor(row.unrealized_pnl) }}>
          {formatUsd(row.unrealized_pnl)}
        </td>
        <td className="tabular">{formatNum(row.unrealized_r, 2)}R</td>
        <td className="tabular text-[11px]">{row.opened_at?.slice(0, 10) ?? "—"}</td>
        <td></td>
        <td>
          <div className="flex items-center gap-1">
            <button
              type="button"
              className="td-btn td-btn-primary text-[11px] px-2 py-0.5"
              disabled={updating}
              onClick={() => void saveEdit()}
            >
              Save
            </button>
            <button
              type="button"
              className="td-btn td-btn-ghost text-[11px] px-2 py-0.5"
              disabled={updating}
              onClick={() => setIsEditing(false)}
            >
              Cancel
            </button>
          </div>
        </td>
      </tr>
    );
  }

  return (
    <tr>
      <td>
        <div className="flex flex-col gap-0.5">
          <Link href={liveHref(row.symbol)} className="no-underline font-semibold" title="Open execution decision">
            {row.symbol}
          </Link>
          <Link
            href={analyzeHref({ symbol: row.symbol })}
            className="no-underline text-[10px]"
            style={{ color: "var(--td-ink-400)" }}
          >
            Analyze
          </Link>
        </div>
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
        <div className="flex items-center gap-1">
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
              <button
                type="button"
                className="td-btn td-btn-ghost text-[11px]"
                onClick={() => setShowClose(false)}
              >
                Cancel
              </button>
            </div>
          ) : (
            <>
              <button
                type="button"
                className="td-btn td-btn-ghost text-[11px] px-1"
                onClick={() => setShowClose(true)}
              >
                Close
              </button>
              <button
                type="button"
                className="td-btn td-btn-ghost text-[11px] px-1"
                onClick={() => setIsEditing(true)}
              >
                Edit
              </button>
              <button
                type="button"
                className="td-btn td-btn-ghost text-[11px] px-1 text-[var(--td-avoid)]"
                onClick={() => void deleteRow()}
              >
                Delete
              </button>
            </>
          )}
        </div>
      </td>
    </tr>
  );
}


export function PositionsTable({
  positions,
  statsRows,
  onClose,
  onUpdate,
  onDelete,
  closingId,
  mode = "all",
}: PositionsTableProps) {
  const showOpen = mode === "open" || mode === "all";
  const showHistory = mode === "history" || mode === "all";
  const open = showOpen ? positions.filter((p) => p.status === "open") : [];
  const closed = showHistory
    ? positions.filter((p) => p.status === "closed")
    : [];

  if (positions.length === 0) {
    return (
      <p className="text-[13px]" style={{ color: "var(--td-ink-300)" }}>
        No paper trades yet — log one from Analyze → Verdict → Log paper trade,
        or from Execution → Decision when gates pass.
      </p>
    );
  }

  if (showOpen && open.length === 0 && !showHistory) {
    return (
      <p className="text-[13px]" style={{ color: "var(--td-ink-300)" }}>
        No open paper positions. Closed history is under History / Risk.
      </p>
    );
  }

  if (showHistory && closed.length === 0 && statsRows.length === 0 && !showOpen) {
    return (
      <p className="text-[13px]" style={{ color: "var(--td-ink-300)" }}>
        No closed trades or model stats yet. Close an open position to record
        outcomes.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {showOpen && open.length > 0 ? (
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
                  onUpdate={onUpdate}
                  onDelete={onDelete}
                  closing={closingId === row.id}
                />
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {showHistory && closed.length > 0 ? (
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

      {showHistory && statsRows.length > 0 ? (
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
