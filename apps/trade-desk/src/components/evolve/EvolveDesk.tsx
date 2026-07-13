"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  AuditReport,
  EvolveBrain,
  EvolveRow,
  EvolveRunSummary,
} from "@/lib/evolve";
import type { ApiEnvelope } from "@/lib/types";
import { modelHref } from "@/lib/routes";
import { PageHeader } from "@/components/shell/PageHeader";

type BoardPayload = {
  run: EvolveRunSummary | null;
  runs: Array<{ id: string; mtime: number; hasState: boolean }>;
  winners: { equity: string | null; options: string | null };
  summary_path: string | null;
  brain?: EvolveBrain | null;
  audits?: AuditReport[];
  ran?: string;
};

async function fetchBoard(run?: string): Promise<BoardPayload> {
  const qs = run ? `?run=${encodeURIComponent(run)}` : "";
  const res = await fetch(`/api/evolve${qs}`, { cache: "no-store" });
  const body = (await res.json()) as ApiEnvelope<BoardPayload>;
  if (!body.ok) throw new Error(body.error || "Failed to load evolve board");
  return body.data as BoardPayload;
}

function claimStyle(level?: string): { bg: string; fg: string } {
  switch (level) {
    case "CLAIM":
      return { bg: "var(--td-badge-winner-bg)", fg: "var(--td-action-buy-now)" };
    case "RESEARCH":
      return { bg: "var(--td-ink-800)", fg: "var(--td-action-breakout-watch)" };
    case "THIN":
      return { bg: "var(--td-ink-800)", fg: "var(--td-ink-400)" };
    case "ERROR":
    case "BLOCKED_DATA":
      return { bg: "var(--td-ink-800)", fg: "var(--td-action-avoid)" };
    default:
      return { bg: "var(--td-ink-800)", fg: "var(--td-ink-300)" };
  }
}

function fmtPct(n: number | undefined | null, digits = 1): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}

function fmtNum(n: number | undefined | null, digits = 2): string {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toFixed(digits);
}

function ClaimChip({ level }: { level?: string }) {
  const s = claimStyle(level);
  return (
    <span
      className="inline-flex items-center rounded-sm px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
      style={{ background: s.bg, color: s.fg }}
    >
      {level || "—"}
    </span>
  );
}

function PhaseStrip() {
  const phases = [
    { id: "0", label: "Integrity" },
    { id: "1", label: "Rank farm" },
    { id: "2", label: "Feedback" },
    { id: "3", label: "Options R&D" },
    { id: "4", label: "Meta" },
    { id: "F", label: "Finalize" },
  ];
  return (
    <div className="flex flex-wrap gap-1.5" aria-label="Pipeline phases">
      {phases.map((p, i) => (
        <div
          key={p.id}
          className="flex items-center gap-1.5 text-[11px]"
          style={{ color: "var(--td-ink-300)" }}
        >
          <span
            className="inline-flex h-5 min-w-5 items-center justify-center rounded-sm px-1 font-mono text-[10px] font-semibold"
            style={{
              background: "var(--td-brand-soft)",
              color: "var(--td-brand)",
              border: "1px solid var(--td-border)",
            }}
          >
            {p.id}
          </span>
          <span>{p.label}</span>
          {i < phases.length - 1 ? (
            <span style={{ color: "var(--td-ink-600)" }} aria-hidden>
              →
            </span>
          ) : null}
        </div>
      ))}
    </div>
  );
}

export function EvolveDesk() {
  const [board, setBoard] = useState<BoardPayload | null>(null);
  const [runId, setRunId] = useState<string>("");
  const [track, setTrack] = useState<"equity" | "options">("equity");
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<EvolveRow | null>(null);
  const [audits, setAudits] = useState<AuditReport[]>([]);

  const load = useCallback(async (id?: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchBoard(id || undefined);
      setBoard(data);
      if (data.audits?.length) setAudits(data.audits);
      if (data.run) {
        setRunId(data.run.id);
        setSelected(data.run.ranking[0] ?? null);
        if (data.run.track?.includes("options")) setTrack("options");
        else setTrack("equity");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Load failed");
      setBoard(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const runQuickRank = useCallback(async () => {
    setRunning(true);
    setError(null);
    try {
      const res = await fetch("/api/evolve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "rank", track, quick: true }),
      });
      const body = (await res.json()) as ApiEnvelope<BoardPayload & { ran?: string }>;
      if (!body.ok) throw new Error(body.error || "Rank failed");
      const data = body.data as BoardPayload;
      setBoard(data);
      if (data.run) {
        setRunId(data.run.id);
        setSelected(data.run.ranking[0] ?? null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Rank failed");
    } finally {
      setRunning(false);
    }
  }, [track]);

  const runAudit = useCallback(async () => {
    setRunning(true);
    setError(null);
    try {
      const res = await fetch("/api/evolve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "audit" }),
      });
      const body = (await res.json()) as ApiEnvelope<BoardPayload>;
      if (!body.ok) throw new Error(body.error || "Audit failed");
      const data = body.data as BoardPayload;
      setBoard((prev) => ({
        run: data.run ?? prev?.run ?? null,
        runs: data.runs?.length ? data.runs : prev?.runs || [],
        winners: data.winners || prev?.winners || { equity: null, options: null },
        summary_path: data.summary_path ?? prev?.summary_path ?? null,
        brain: data.brain ?? prev?.brain ?? null,
        audits: data.audits ?? prev?.audits,
      }));
      if (data.audits) setAudits(data.audits);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Audit failed");
    } finally {
      setRunning(false);
    }
  }, []);

  const runTrainEpochs = useCallback(async () => {
    setRunning(true);
    setError(null);
    try {
      const res = await fetch("/api/evolve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "train",
          track,
          epochs: 3,
          base: track === "options" ? "v35_softstruct_bag8" : "v23_devin_overlay",
        }),
      });
      const body = (await res.json()) as ApiEnvelope<BoardPayload>;
      if (!body.ok) throw new Error(body.error || "Train failed");
      const data = body.data as BoardPayload;
      setBoard((prev) => ({
        ...(data || prev),
        brain: data.brain ?? prev?.brain ?? null,
        run: data.run ?? prev?.run ?? null,
        runs: data.runs?.length ? data.runs : prev?.runs || [],
        winners: data.winners || prev?.winners || { equity: null, options: null },
        summary_path: data.summary_path ?? prev?.summary_path ?? null,
      }));
      if (data.run) {
        setRunId(data.run.id);
        setSelected(data.run.ranking[0] ?? null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Train failed");
    } finally {
      setRunning(false);
    }
  }, [track]);

  const ranking = useMemo(() => board?.run?.ranking ?? [], [board?.run?.ranking]);
  const finalize = board?.run?.finalize;
  const winners = board?.winners;

  const maxUtil = useMemo(
    () => Math.max(0.01, ...ranking.map((r) => Math.abs(Number(r.utility) || 0))),
    [ranking],
  );

  return (
    <div className="td-page">
      <PageHeader
        title="Evolve"
        description="Self-feedback train loop: genome knobs update from OOS utility (like training). Primary SIDE stays rules; secondary risk/meta learns."
        meta={<PhaseStrip />}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-1.5 text-[12px]" style={{ color: "var(--td-ink-300)" }}>
              Run
              <select
                className="td-input"
                style={{ minWidth: 180, fontSize: 12 }}
                value={runId}
                onChange={(e) => {
                  const v = e.target.value;
                  setRunId(v);
                  void load(v);
                }}
                disabled={loading || running}
              >
                {(board?.runs || []).map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.id}
                  </option>
                ))}
                {!board?.runs?.length ? <option value="">No runs</option> : null}
              </select>
            </label>
            <label className="flex items-center gap-1.5 text-[12px]" style={{ color: "var(--td-ink-300)" }}>
              Track
              <select
                className="td-input"
                style={{ fontSize: 12 }}
                value={track}
                onChange={(e) => setTrack(e.target.value as "equity" | "options")}
                disabled={running}
              >
                <option value="equity">equity</option>
                <option value="options">options</option>
              </select>
            </label>
            <button
              type="button"
              className="td-btn td-btn-ghost"
              disabled={loading || running}
              onClick={() => void load(runId || undefined)}
            >
              Reload
            </button>
            <button
              type="button"
              className="td-btn td-btn-ghost"
              disabled={loading || running}
              onClick={() => void runQuickRank()}
              title="One-shot board rank"
            >
              Rank
            </button>
            <button
              type="button"
              className="td-btn td-btn-ghost"
              disabled={loading || running}
              onClick={() => void runAudit()}
              title="Independent auditor: overfit, look-ahead, vanity WR, cheating"
            >
              Audit models
            </button>
            <button
              type="button"
              className="td-btn td-btn-primary"
              disabled={loading || running}
              onClick={() => void runTrainEpochs()}
              title="3 train epochs: mutate genome → OOS reward → auditor gate → keep if better"
            >
              {running ? "Working…" : "Train 3 epochs"}
            </button>
          </div>
        }
      />

      {error ? (
        <p className="td-alert td-alert--error" role="alert">
          {error}
        </p>
      ) : null}

      {/* Brain / train state */}
      <div className="mb-3 grid grid-cols-1 gap-2 md:grid-cols-4">
        <div className="td-panel p-3 md:col-span-1">
          <p className="td-eyebrow">Train brain</p>
          <p className="font-mono text-[14px] font-semibold tabular-nums" style={{ color: "var(--td-ink-100)" }}>
            epoch {board?.brain?.epoch ?? 0}
          </p>
          <p className="mt-1 text-[12px]" style={{ color: "var(--td-ink-400)" }}>
            best OOS obj{" "}
            <strong className="tabular-nums" style={{ color: "var(--td-brand)" }}>
              {board?.brain?.best_utility_oos != null
                ? Number(board.brain.best_utility_oos).toFixed(3)
                : "—"}
            </strong>
          </p>
          <p className="mt-1 text-[11px] tabular-nums" style={{ color: "var(--td-ink-500)" }}>
            ✓{board?.brain?.accepted ?? 0} / ✗{board?.brain?.rejected ?? 0}
          </p>
          {board?.brain?.lessons?.length ? (
            <p className="mt-2 text-[11px] leading-snug" style={{ color: "var(--td-ink-400)" }}>
              {board.brain.lessons[board.brain.lessons.length - 1]}
            </p>
          ) : (
            <p className="mt-2 text-[11px]" style={{ color: "var(--td-ink-500)" }}>
              No epochs yet — hit Train to start self-feedback.
            </p>
          )}
        </div>
        <div className="td-panel p-3">
          <p className="td-eyebrow">Finalize</p>
          <p
            className="font-mono text-[14px] font-semibold tabular-nums"
            style={{ color: "var(--td-ink-100)" }}
          >
            {finalize?.action || (loading ? "…" : "—")}
          </p>
          <p className="mt-1 text-[12px]" style={{ color: "var(--td-ink-400)" }}>
            Top:{" "}
            <span style={{ color: "var(--td-ink-200)" }}>
              {finalize?.top_evolve || board?.run?.ranking?.[0]?.id || "—"}
            </span>
            {finalize?.top_utility != null
              ? ` · util ${fmtNum(finalize.top_utility, 3)}`
              : null}
          </p>
          {finalize?.reasons?.length ? (
            <ul className="mt-2 space-y-0.5 text-[11px]" style={{ color: "var(--td-ink-400)" }}>
              {finalize.reasons.slice(0, 3).map((r) => (
                <li key={r}>· {r}</li>
              ))}
            </ul>
          ) : null}
        </div>
        <div className="td-panel p-3">
          <p className="td-eyebrow">Frozen equity WINNER</p>
          <p className="font-mono text-[14px] font-semibold" style={{ color: "var(--td-brand)" }}>
            {winners?.equity || "—"}
          </p>
          <Link
            href={winners?.equity ? modelHref(winners.equity) : "/leaderboard"}
            className="mt-2 inline-block text-[12px] no-underline"
            style={{ color: "var(--td-ink-300)" }}
          >
            Open model →
          </Link>
        </div>
        <div className="td-panel p-3">
          <p className="td-eyebrow">OPTIONS_WINNER (research)</p>
          <p className="font-mono text-[14px] font-semibold" style={{ color: "var(--td-ink-200)" }}>
            {winners?.options || "—"}
          </p>
          <p className="mt-1 text-[11px]" style={{ color: "var(--td-ink-500)" }}>
            Synthetic BS · never auto-promote
          </p>
        </div>
      </div>

      {/* Auditor panel */}
      {audits.length > 0 ? (
        <div className="td-panel mb-3 overflow-hidden">
          <div
            className="flex items-center justify-between border-b px-3 py-2"
            style={{ borderColor: "var(--td-border)" }}
          >
            <div>
              <p className="td-eyebrow">Auditor model</p>
              <p className="text-[13px]" style={{ color: "var(--td-ink-200)" }}>
                Independent checks — overfit, look-ahead, vanity metrics, options fantasy
              </p>
            </div>
            <span className="text-[11px] tabular-nums" style={{ color: "var(--td-ink-500)" }}>
              {audits.length} reports
            </span>
          </div>
          <div className="max-h-56 overflow-y-auto">
            <table className="w-full border-collapse text-left text-[12px]">
              <thead>
                <tr
                  className="border-b text-[10px] uppercase tracking-wide"
                  style={{ borderColor: "var(--td-border)", color: "var(--td-ink-400)" }}
                >
                  <th className="px-3 py-1.5 font-medium">Verdict</th>
                  <th className="px-3 py-1.5 font-medium">Score</th>
                  <th className="px-3 py-1.5 font-medium">Target</th>
                  <th className="px-3 py-1.5 font-medium">Flags</th>
                </tr>
              </thead>
              <tbody>
                {audits.map((a) => {
                  const vcol =
                    a.verdict === "PASS"
                      ? "var(--td-gate-pass)"
                      : a.verdict === "WARN"
                        ? "var(--td-action-breakout-watch)"
                        : "var(--td-action-avoid)";
                  const flags = (a.findings || [])
                    .filter((f) => f.severity !== "info")
                    .map((f) => f.code)
                    .slice(0, 6);
                  return (
                    <tr
                      key={a.target}
                      className="border-b"
                      style={{ borderColor: "var(--td-border)" }}
                    >
                      <td className="px-3 py-1.5 font-semibold" style={{ color: vcol }}>
                        {a.verdict}
                      </td>
                      <td className="px-3 py-1.5 font-mono tabular-nums">
                        {Number(a.score).toFixed(0)}
                      </td>
                      <td className="px-3 py-1.5 font-mono" style={{ color: "var(--td-ink-100)" }}>
                        {a.target}
                      </td>
                      <td className="px-3 py-1.5" style={{ color: "var(--td-ink-400)" }}>
                        {flags.length ? flags.join(", ") : "clean"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {/* Meta strip */}
      <div
        className="mb-3 flex flex-wrap items-center gap-3 border px-3 py-2 text-[12px]"
        style={{
          borderColor: "var(--td-border)",
          background: "var(--td-ink-900)",
          color: "var(--td-ink-300)",
        }}
      >
        <span>
          Track{" "}
          <strong style={{ color: "var(--td-ink-100)" }}>
            {board?.run?.track || "—"}
          </strong>
        </span>
        <span aria-hidden>·</span>
        <span>
          Cash{" "}
          <strong className="tabular-nums" style={{ color: "var(--td-ink-100)" }}>
            {board?.run?.cash != null
              ? `$${board.run.cash.toLocaleString()}`
              : "—"}
          </strong>
        </span>
        <span aria-hidden>·</span>
        <span>
          Updated{" "}
          <strong className="tabular-nums" style={{ color: "var(--td-ink-100)" }}>
            {board?.run?.updated_at
              ? new Date(board.run.updated_at).toLocaleString()
              : "—"}
          </strong>
        </span>
        <span aria-hidden>·</span>
        <span className="font-mono text-[11px]">{board?.run?.path || "—"}</span>
        {board?.run?.promote?.length ? (
          <>
            <span aria-hidden>·</span>
            <span>
              Promote{" "}
              {board.run.promote.map((p) => (
                <ClaimChip key={p} level="CLAIM" />
              ))}{" "}
              <span style={{ color: "var(--td-ink-200)" }}>
                {board.run.promote.join(", ")}
              </span>
            </span>
          </>
        ) : null}
      </div>

      <div className="td-panel grid grid-cols-1 overflow-hidden lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="min-w-0 overflow-x-auto">
          {loading && !ranking.length ? (
            <div className="p-8 text-[13px]" style={{ color: "var(--td-ink-400)" }}>
              Loading evolve board…
            </div>
          ) : !ranking.length ? (
            <div className="p-8 text-[13px]" style={{ color: "var(--td-ink-400)" }}>
              No ranking rows. Run quick rank or generate via CLI:
              <pre className="mt-2 overflow-x-auto text-[11px]" style={{ color: "var(--td-ink-300)" }}>
                {`.venv/bin/python tools/evolve_pipeline.py rank --track equity --cash 10000`}
              </pre>
            </div>
          ) : (
            <table className="w-full border-collapse text-left text-[12px]">
              <thead>
                <tr
                  className="border-b text-[10px] uppercase tracking-wide"
                  style={{
                    borderColor: "var(--td-border)",
                    color: "var(--td-ink-400)",
                  }}
                >
                  <th className="px-2 py-2 font-medium">#</th>
                  <th className="px-2 py-2 font-medium">Model</th>
                  <th className="px-2 py-2 font-medium">Claim</th>
                  <th className="px-2 py-2 font-medium">Mode</th>
                  <th className="px-2 py-2 font-medium tabular-nums">Util</th>
                  <th className="px-2 py-2 font-medium tabular-nums">Ret</th>
                  <th className="px-2 py-2 font-medium tabular-nums">Sharpe</th>
                  <th className="px-2 py-2 font-medium tabular-nums">DD</th>
                  <th className="px-2 py-2 font-medium tabular-nums">n</th>
                  <th className="px-2 py-2 font-medium">OOS lock</th>
                  <th className="px-2 py-2 font-medium">Util bar</th>
                </tr>
              </thead>
              <tbody>
                {ranking.map((row, i) => {
                  const active = selected?.id === row.id;
                  const util = Number(row.utility) || 0;
                  const barW = Math.min(100, Math.max(0, (Math.abs(util) / maxUtil) * 100));
                  return (
                    <tr
                      key={`${row.id}-${i}`}
                      className="cursor-pointer border-b transition-colors"
                      style={{
                        borderColor: "var(--td-border)",
                        background: active
                          ? "var(--td-brand-soft)"
                          : i % 2
                            ? "var(--td-ink-900)"
                            : "transparent",
                      }}
                      onClick={() => setSelected(row)}
                    >
                      <td
                        className="px-2 py-1.5 font-mono tabular-nums"
                        style={{
                          color:
                            i === 0
                              ? "var(--td-rank-gold)"
                              : i === 1
                                ? "var(--td-rank-silver)"
                                : "var(--td-ink-400)",
                        }}
                      >
                        {i + 1}
                      </td>
                      <td className="px-2 py-1.5 font-mono text-[12px]" style={{ color: "var(--td-ink-100)" }}>
                        {row.id}
                        {row.may_auto_promote ? (
                          <span
                            className="ml-1.5 text-[9px] uppercase"
                            style={{ color: "var(--td-action-buy-now)" }}
                          >
                            promote
                          </span>
                        ) : null}
                      </td>
                      <td className="px-2 py-1.5">
                        <ClaimChip level={row.claim_level} />
                      </td>
                      <td className="px-2 py-1.5" style={{ color: "var(--td-ink-400)" }}>
                        {row.mode || "—"}
                      </td>
                      <td
                        className="px-2 py-1.5 font-mono tabular-nums"
                        style={{
                          color: util < 0 ? "var(--td-action-avoid)" : "var(--td-ink-100)",
                        }}
                      >
                        {fmtNum(util, 3)}
                      </td>
                      <td className="px-2 py-1.5 font-mono tabular-nums">
                        {fmtPct(row.ret)}
                      </td>
                      <td className="px-2 py-1.5 font-mono tabular-nums">
                        {fmtNum(row.sharpe)}
                      </td>
                      <td
                        className="px-2 py-1.5 font-mono tabular-nums"
                        style={{ color: "var(--td-action-avoid)" }}
                      >
                        {fmtPct(row.dd)}
                      </td>
                      <td className="px-2 py-1.5 font-mono tabular-nums">
                        {row.n ?? "—"}
                      </td>
                      <td className="px-2 py-1.5">
                        {row.multi_lock ? (
                          <span
                            style={{
                              color:
                                row.multi_lock === "PASS"
                                  ? "var(--td-gate-pass)"
                                  : row.multi_lock === "FAIL"
                                    ? "var(--td-gate-fail)"
                                    : "var(--td-ink-400)",
                            }}
                          >
                            {row.multi_lock}
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="px-2 py-1.5" style={{ minWidth: 72 }}>
                        <div
                          className="h-1.5 w-full overflow-hidden rounded-sm"
                          style={{ background: "var(--td-score-track)" }}
                        >
                          <div
                            className="h-full rounded-sm"
                            style={{
                              width: `${barW}%`,
                              background:
                                util < 0
                                  ? "var(--td-action-avoid)"
                                  : "var(--td-score-bar)",
                            }}
                          />
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Side panel */}
        <aside
          className="border-t p-3 lg:border-l lg:border-t-0"
          style={{ borderColor: "var(--td-border)", background: "var(--td-ink-900)" }}
        >
          {selected ? (
            <>
              <p className="td-eyebrow">Selected</p>
              <h2
                className="font-mono text-[15px] font-semibold"
                style={{ color: "var(--td-ink-50)" }}
              >
                {selected.id}
              </h2>
              <div className="mt-2 flex flex-wrap gap-1">
                <ClaimChip level={selected.claim_level} />
                {selected.may_auto_promote ? (
                  <ClaimChip level="CLAIM" />
                ) : null}
              </div>
              <dl className="mt-3 space-y-1.5 text-[12px]">
                {[
                  ["Utility", fmtNum(selected.utility, 3)],
                  ["Return", fmtPct(selected.ret)],
                  ["Sharpe", fmtNum(selected.sharpe)],
                  ["Max DD", fmtPct(selected.dd)],
                  ["Trades", String(selected.n ?? "—")],
                  ["WR", fmtPct(selected.wr)],
                  ["Track", selected.data_track || "—"],
                  ["Mode", selected.mode || "—"],
                  ["Multi-lock", selected.multi_lock || "—"],
                ].map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-2">
                    <dt style={{ color: "var(--td-ink-500)" }}>{k}</dt>
                    <dd className="font-mono tabular-nums" style={{ color: "var(--td-ink-200)" }}>
                      {v}
                    </dd>
                  </div>
                ))}
              </dl>
              {selected.pass_bar?.reasons?.length ? (
                <div className="mt-3">
                  <p className="text-[10px] uppercase" style={{ color: "var(--td-ink-500)" }}>
                    PASS_BAR gaps
                  </p>
                  <ul className="mt-1 space-y-0.5 text-[11px]" style={{ color: "var(--td-action-avoid)" }}>
                    {selected.pass_bar.reasons.map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              <div className="mt-4 flex flex-col gap-2">
                <Link
                  href={modelHref(selected.id)}
                  className="td-btn td-btn-primary no-underline text-center"
                >
                  Open model
                </Link>
                <Link
                  href={`/?model=${encodeURIComponent(selected.id)}`}
                  className="td-btn td-btn-ghost no-underline text-center"
                >
                  Analyze with model
                </Link>
                <Link
                  href="/leaderboard"
                  className="td-btn td-btn-ghost no-underline text-center"
                >
                  Registry leaderboard
                </Link>
              </div>
            </>
          ) : (
            <p className="text-[13px]" style={{ color: "var(--td-ink-400)" }}>
              Select a row for claim detail and actions.
            </p>
          )}
        </aside>
      </div>

      <p className="mt-3 text-[11px]" style={{ color: "var(--td-ink-500)" }}>
        Self-train accepts only OOS utility gains (anti-overfit). Genome = risk/meta knobs, not primary
        SIDE. CLI:{" "}
        <code className="font-mono">
          tools/evolve_pipeline.py train --epochs 20 --base v23_devin_overlay
        </code>
        {" · "}
        <code className="font-mono">train --continuous --max-epochs 100</code>
        {board?.summary_path ? (
          <>
            {" "}
            · summary <code className="font-mono">{board.summary_path}</code>
          </>
        ) : null}
      </p>
    </div>
  );
}
