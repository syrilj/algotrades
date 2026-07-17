"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";

import { formatNum, formatPct, formatUsd } from "@/lib/format";
import { analyzeHref, modelHref } from "@/lib/routes";
import { colorVarFor } from "@/lib/actionColors";
import type {
  ApiEnvelope,
  ClaimLevel,
  RankerRead,
  RankerResponse,
  RankerRow,
} from "@/lib/types";

type RankerPanelProps = {
  symbol: string;
  account: number;
  activeModel?: string;
  onUseModel: (model: string) => void;
};

function claimChipStyle(level: ClaimLevel): CSSProperties {
  const u = String(level).toUpperCase();
  if (u === "CLAIM") return { color: "var(--td-action-buy-now)" };
  if (u === "RESEARCH") return { color: "var(--td-action-wait)" };
  return { color: "var(--td-ink-500)" };
}

function scoreBarColor(score: number): string {
  return score >= 0 ? "var(--td-action-buy-now)" : "var(--td-action-avoid)";
}

/** Evidence-gate reason codes → operator-readable labels (tools/symbol_ranker.py). */
const REASON_LABELS: Record<string, string> = {
  no_valid_full_window: "No valid full-window backtest",
  no_trades: "No trades in evidence window",
  win_rate_lb_below_breakeven: "Win-rate lower bound below breakeven",
  recent_window_negative: "Recent window return negative",
  drawdown_gate: "Max drawdown exceeds risk gate",
  live_underperformance: "Live paper trading underperforming",
  thin_sample_capped: "Confidence capped — thin sample size",
  synthetic_options_pricing_capped: "Confidence capped — synthetic options pricing",
  ranker_stale_refresh_required: "Ranker cache stale — refresh required",
  no_desk_runnable_evidence: "No desk-runnable engine evidence",
  sample_below_trust_floor: "Sample size below trust floor",
  confidence_below_watch_threshold: "Confidence below watch threshold",
};

/** Honest fallback for any reason code not yet in the label map above. */
function humanizeReason(code: string): string {
  const known = REASON_LABELS[code];
  if (known) return known;
  const spaced = code.replace(/_/g, " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/**
 * verdict → action color token. Reuses the shared action-color map (same
 * tokens as ActionChip / OptionsDesk) by piggy-backing on the closest
 * existing semantic key: TRUST=buy/positive, WATCH=wait, STAND_ASIDE=avoid.
 */
function verdictColorVar(verdict: RankerRead["verdict"] | undefined): string {
  if (verdict === "TRUST") return colorVarFor("action", "RISK_OK");
  if (verdict === "WATCH") return colorVarFor("action", "WATCH");
  return colorVarFor("action", "STAND_ASIDE");
}

function verdictLabel(verdict: RankerRead["verdict"] | undefined): string {
  return String(verdict ?? "STAND_ASIDE").replace(/_/g, " ");
}

function VerdictStrip({ read }: { read: RankerRead }) {
  const color = verdictColorVar(read.verdict);
  const isStandAside = read.verdict === "STAND_ASIDE";
  const reasons = read.reasons ?? [];

  return (
    <div
      className="mb-3 flex flex-col gap-2 border-l-2 px-3 py-2"
      style={{
        borderColor: color,
        background: `color-mix(in oklch, ${color} 8%, transparent)`,
      }}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span
          className="td-action-chip td-action-chip--md"
          style={{
            color,
            background: `color-mix(in oklch, ${color} 18%, transparent)`,
            border: `1px solid ${color}`,
          }}
        >
          {verdictLabel(read.verdict)}
        </span>
        {read.model ? (
          <Link
            href={modelHref(read.model)}
            className="tabular no-underline text-[13px]"
            style={{ fontFamily: "var(--td-font-mono)", color: "var(--td-ink-100)" }}
          >
            {read.model}
          </Link>
        ) : (
          <span className="text-[12px]" style={{ color: "var(--td-ink-500)" }}>
            no engine cleared evidence
          </span>
        )}
        <span
          className="tabular ml-auto shrink-0 text-[12px] font-semibold"
          style={{ fontFamily: "var(--td-font-mono)", color }}
        >
          {formatPct(read.confidence)} confidence
        </span>
      </div>

      {isStandAside && reasons.length > 0 ? (
        <ul
          className="m-0 flex list-none flex-col gap-0.5 p-0 text-[11px] leading-snug"
          style={{ color: "var(--td-ink-400)" }}
        >
          {reasons.map((r) => (
            <li key={r}>— {humanizeReason(r)}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function RankerRowCard({
  row,
  maxScore,
  account,
  activeModel,
  onUseModel,
}: {
  row: RankerRow;
  maxScore: number;
  account: number;
  activeModel?: string;
  onUseModel: (model: string) => void;
}) {
  const barPct = maxScore > 0 ? Math.min(100, (Math.abs(row.score) / maxScore) * 100) : 0;
  const inUse = activeModel === row.model;
  const live = row.live;
  const confDim = row.confidence == null || row.confidence === 0;
  const confReasons = row.confidence_reasons ?? [];
  const confTitle = confReasons.length > 0 ? confReasons.map(humanizeReason).join("; ") : undefined;

  return (
    <li
      className="flex flex-col gap-2 border-b py-3 last:border-b-0"
      style={{ borderColor: "var(--td-ink-700)" }}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span
          className="tabular text-[12px] font-semibold"
          style={{
            color: row.rank === 1 ? "var(--td-rank-gold)" : "var(--td-ink-400)",
            fontFamily: "var(--td-font-mono)",
          }}
        >
          #{row.rank}
        </span>
        <Link
          href={modelHref(row.model)}
          className="no-underline text-[13px]"
          style={{ fontFamily: "var(--td-font-mono)", color: "var(--td-ink-100)" }}
        >
          {row.model}
        </Link>
        <span
          className="td-chip text-[10px]"
          style={claimChipStyle(row.claim_level)}
        >
          {row.claim_level}
        </span>
        {live && live.n > 0 ? (
          <span
            className="td-chip text-[10px]"
            style={{ color: "var(--td-ink-200)" }}
          >
            LIVE {live.wins}-{live.n - live.wins}{" "}
            {live.total_pnl >= 0 ? "+" : ""}
            {formatUsd(live.total_pnl, 0)}
          </span>
        ) : null}
        <div className="ml-auto">
          {inUse ? (
            <span className="text-[11px]" style={{ color: "var(--td-ink-400)" }}>
              In use
            </span>
          ) : (
            <button
              type="button"
              className="td-btn td-btn-ghost"
              disabled={!row.desk_runnable}
              title={
                row.desk_runnable
                  ? `Analyze with ${row.model}`
                  : "backtest-only engine (not desk-runnable)"
              }
              onClick={() => onUseModel(row.model)}
            >
              Use model
            </button>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <div
          className="h-1.5 flex-1 overflow-hidden rounded-sm"
          style={{ background: "var(--td-ink-700)" }}
        >
          <div
            className="h-full"
            style={{ width: `${barPct}%`, background: scoreBarColor(row.score) }}
          />
        </div>
        <span
          className="tabular shrink-0 text-[11px]"
          style={{ fontFamily: "var(--td-font-mono)", color: "var(--td-ink-300)" }}
        >
          {formatNum(row.score, 2)}
        </span>
      </div>

      <div
        className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] tabular"
        style={{ fontFamily: "var(--td-font-mono)", color: "var(--td-ink-400)" }}
      >
        <span>Ret {formatPct(row.total_return)}</span>
        <span>
          ≈6mo @ acct{" "}
          {row.proj_6mo_return != null
            ? formatUsd(row.proj_6mo_return * account, 0)
            : "—"}
        </span>
        <span>WR {formatPct(row.win_rate, 0)}</span>
        <span>DD {formatPct(row.max_drawdown, 1)}</span>
        <span>n {row.trade_count ?? "—"}</span>
        <span
          title={confTitle}
          style={confDim ? { color: "var(--td-ink-500)" } : undefined}
        >
          Conf {row.confidence != null ? formatPct(row.confidence, 0) : "—"}
        </span>
      </div>
    </li>
  );
}

export function RankerPanel({
  symbol,
  account,
  activeModel,
  onUseModel,
}: RankerPanelProps) {
  const [data, setData] = useState<RankerResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [ranking, setRanking] = useState(false);

  const sym = symbol.trim().toUpperCase();

  const fetchShow = useCallback(async () => {
    if (!sym) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/symbol-rank?symbol=${encodeURIComponent(sym)}`);
      const json = (await res.json()) as ApiEnvelope<RankerResponse>;
      if (!res.ok || json.ok === false || !json.data) {
        throw new Error(json.error ?? `Rank fetch failed (${res.status})`);
      }
      setData(json.data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Rank fetch failed");
    } finally {
      setLoading(false);
    }
  }, [sym]);

  useEffect(() => {
    void fetchShow();
  }, [fetchShow]);

  const deepRank = useCallback(async () => {
    if (!sym) return;
    setRanking(true);
    setError(null);
    try {
      const res = await fetch("/api/symbol-rank", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: sym, maxSeconds: 240 }),
      });
      const json = (await res.json()) as ApiEnvelope<RankerResponse>;
      if (!res.ok || json.ok === false || !json.data) {
        throw new Error(json.error ?? `Deep rank failed (${res.status})`);
      }
      setData(json.data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Deep rank failed");
      await fetchShow();
    } finally {
      setRanking(false);
    }
  }, [sym, fetchShow]);

  const topRows = useMemo(() => (data?.rows ?? []).slice(0, 4), [data]);
  const maxScore = useMemo(
    () => Math.max(0.01, ...topRows.map((r) => Math.abs(r.score))),
    [topRows],
  );

  if (!sym) return null;

  return (
    <section className="td-panel p-4" aria-label={`Symbol ranker for ${sym}`}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <span className="td-label">Best engine for {sym}</span>
          <p className="text-[13px]" style={{ color: "var(--td-ink-300)" }}>
            Return-forward backtest
            {data?.asof ? (
              <span
                className="ml-2 tabular text-[11px]"
                style={{ fontFamily: "var(--td-font-mono)", color: "var(--td-ink-500)" }}
              >
                {data.asof.slice(0, 19).replace("T", " ")}Z
              </span>
            ) : null}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {data?.stale ? (
            <span className="td-chip td-chip--warn text-[10px]">STALE</span>
          ) : null}
          {data?.status === "partial" ? (
            <span className="text-[11px]" style={{ color: "var(--td-action-wait)" }}>
              partial — run again to finish
            </span>
          ) : null}
          <button
            type="button"
            className="td-btn td-btn-ghost"
            disabled={ranking}
            onClick={() => void deepRank()}
          >
            {ranking
              ? "Backtesting N engines × 3 windows… ~2–4 min"
              : "Deep rank"}
          </button>
        </div>
      </div>

      {data?.read ? <VerdictStrip read={data.read} /> : null}

      {error ? (
        <div className="td-alert td-alert--error mb-3" role="alert">
          {error}
        </div>
      ) : null}

      {loading && !data ? (
        <p className="text-[13px]" style={{ color: "var(--td-ink-400)" }}>
          Loading ranker cache…
        </p>
      ) : null}

      {data && data.exists === false ? (
        <div className="flex flex-col gap-3">
          <p className="text-[13px]" style={{ color: "var(--td-ink-300)" }}>
            No ranker cache for {sym}. Deep rank backtests every desk engine on this
            symbol (2–4 min).
          </p>
          <button
            type="button"
            className="td-btn td-btn-primary self-start"
            disabled={ranking}
            onClick={() => void deepRank()}
          >
            Deep rank
          </button>
        </div>
      ) : null}

      {topRows.length > 0 ? (
        <ul className="mt-1 list-none p-0">{topRows.map((row) => (
          <RankerRowCard
            key={row.model}
            row={row}
            maxScore={maxScore}
            account={account}
            activeModel={activeModel}
            onUseModel={onUseModel}
          />
        ))}</ul>
      ) : null}

      {data?.options_rows && data.options_rows.length > 0 ? (
        <details className="td-details mt-3">
          <summary className="td-details__summary">
            Options engines (bag symbol) · synthetic pricing · research only
          </summary>
          <ul className="mt-2 list-none p-0">
            {data.options_rows.slice(0, 4).map((row) => (
              <RankerRowCard
                key={`opt-${row.model}`}
                row={row}
                maxScore={maxScore}
                account={account}
                activeModel={activeModel}
                onUseModel={onUseModel}
              />
            ))}
          </ul>
        </details>
      ) : null}

      <p className="mt-2 text-[11px]" style={{ color: "var(--td-ink-500)" }}>
        <Link href={analyzeHref({ symbol: sym })} className="no-underline">
          Analyze {sym}
        </Link>
      </p>
    </section>
  );
}
