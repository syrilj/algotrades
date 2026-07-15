"use client";

import { ActionChip } from "@/components/ui/ActionChip";
import { Stat } from "@/components/ui/Stat";
import { ModelFlow } from "@/components/models/ModelFlow";
import type { AnalysisReport as AnalysisReportType } from "@/lib/types";

function fmt(n: number | null | undefined, digits = 2): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return n.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function fmtUsd(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

function fmtPct(n: number | null | undefined, digits = 1): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}

function impactColor(impact: string): string {
  if (impact === "positive") return "var(--td-success)";
  if (impact === "negative") return "var(--td-m-red)";
  return "var(--td-muted)";
}

function driverLabelColor(impact: string): string {
  if (impact === "positive") return "var(--td-success)";
  if (impact === "negative") return "var(--td-m-red)";
  return "var(--td-ink-400)";
}

type AnalysisReportProps = {
  symbol: string;
  model: string | null;
  report: AnalysisReportType;
};

export function AnalysisReport({ symbol, model, report }: AnalysisReportProps) {
  const { facts, decision, suggestion } = report;
  const live = facts.live;
  const macro = facts.macro;
  const gex = facts.gex;
  const m = facts.model;
  const ticket = suggestion.ticket;

  return (
    <div className="flex flex-col gap-4">
      {/* Verdict */}
      <section
        className="td-panel"
        style={{
          borderLeft: "4px solid var(--td-brand)",
        }}
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex flex-col gap-1">
            <span className="td-label">Analysis Agent</span>
            <div className="flex flex-wrap items-baseline gap-3">
              <span
                className="text-[18px] font-medium"
                style={{ fontFamily: "var(--td-font-mono)", color: "var(--td-ink-100)" }}
              >
                {symbol}
              </span>
              <span
                className="text-[16px]"
                style={{ fontFamily: "var(--td-font-mono)", color: "var(--td-ink-300)" }}
              >
                {facts.price ? fmtUsd(facts.price) : "—"}
              </span>
              {model ? (
                <span
                  className="text-[11px]"
                  style={{ fontFamily: "var(--td-font-mono)", color: "var(--td-ink-400)" }}
                >
                  {model}
                </span>
              ) : null}
            </div>
          </div>
          <ActionChip action={decision.action || "WAIT"} size="lg" />
        </div>

        <p
          className="mt-3 text-[14px] leading-relaxed"
          style={{ color: "var(--td-ink-200)" }}
        >
          {suggestion.rationale}
        </p>

        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Confidence" value={decision.confidence_state || "—"} emphasize />
          <Stat label="Mode" value={decision.mode || "—"} emphasize />
          <Stat label="Risk" value={fmtPct(decision.risk_pct, 2)} emphasize />
          <Stat label="Max loss" value={fmtUsd(decision.max_loss_dollars)} emphasize />
        </div>
      </section>

      {/* Facts dashboard */}
      <section className="td-panel">
        <div className="mb-3 flex items-baseline justify-between gap-3">
          <h2 className="text-[14px] font-medium" style={{ color: "var(--td-ink-100)" }}>
            Facts
          </h2>
          <span
            className="text-[10px]"
            style={{ fontFamily: "var(--td-font-mono)", color: "var(--td-ink-500)" }}
          >
            {facts.asof_utc}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Live vol_z" value={fmt(live.vol_z, 2)} emphasize />
          <Stat label="ATR %" value={fmt(live.atr_pct, 4)} emphasize />
          <Stat label="MACD" value={live.macd_positive ? "positive" : "negative"} emphasize />
          <Stat label="VWAP" value={live.above_vwap ? "above" : "below"} emphasize />
          <Stat label="Swing trend" value={live.swing_uptrend ? "up" : "down"} emphasize />
          <Stat label="Signal strength" value={fmt(live.signal_strength, 1)} emphasize />
          <Stat label="QQQ trend" value={macro.qqq_trend || "—"} emphasize />
          <Stat label="Macro" value={macro.xlp_spy_ratio_state || "—"} emphasize />
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 border-t border-dashed pt-4 md:grid-cols-4" style={{ borderColor: "var(--td-hairline)" }}>
          <Stat label="GEX regime" value={gex.regime || "—"} emphasize />
          <Stat label="Call wall" value={fmtUsd(gex.call_wall)} emphasize />
          <Stat label="Put wall" value={fmtUsd(gex.put_wall)} emphasize />
          <Stat label="Flip strike" value={fmtUsd(gex.approx_flip_strike)} emphasize />
          <Stat label="Spot" value={fmtUsd(gex.spot)} emphasize />
          <Stat label="Exp move" value={fmtPct(gex.expected_move_pct, 2)} emphasize />
          <Stat label="Max pain" value={fmtUsd(gex.max_pain)} emphasize />
          <Stat label="Squeeze" value={gex.squeeze_label || "neutral"} emphasize />
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 border-t border-dashed pt-4 md:grid-cols-4" style={{ borderColor: "var(--td-hairline)" }}>
          <Stat label="Model" value={m.model || "—"} emphasize />
          <Stat label="Model conf" value={fmt(m.confidence, 2)} emphasize />
          <Stat label="Setup" value={m.setup_ok ? "ok" : m.setup_ok === false ? "not ok" : "—"} emphasize />
          <Stat label="Entry / stop" value={`${fmtUsd(m.entry)} / ${fmtUsd(m.stop)}`} emphasize />
        </div>
      </section>

      {/* Model leaderboard */}
      <section className="td-panel">
        <h2 className="mb-3 text-[14px] font-medium" style={{ color: "var(--td-ink-100)" }}>
          Top models for {symbol}
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full text-left" style={{ fontSize: "12px" }}>
            <thead>
              <tr style={{ color: "var(--td-ink-500)" }}>
                <th className="py-1 pr-3 font-medium">Rank</th>
                <th className="py-1 pr-3 font-medium">Model</th>
                <th className="py-1 pr-3 font-medium">WR</th>
                <th className="py-1 pr-3 font-medium">Sharpe</th>
                <th className="py-1 pr-3 font-medium">Return</th>
                <th className="py-1 pr-3 font-medium">Max DD</th>
                <th className="py-1 pr-3 font-medium">Trades</th>
                <th className="py-1 pr-3 font-medium">Score</th>
              </tr>
            </thead>
            <tbody style={{ color: "var(--td-ink-200)" }}>
              {facts.top_models.map((row) => (
                <tr key={row.model} className="border-t" style={{ borderColor: "var(--td-hairline)" }}>
                  <td className="py-1.5 pr-3 tabular" style={{ fontFamily: "var(--td-font-mono)" }}>
                    {row.rank}
                  </td>
                  <td className="py-1.5 pr-3" style={{ fontFamily: "var(--td-font-mono)" }}>
                    {row.model}
                  </td>
                  <td className="py-1.5 pr-3 tabular">{fmtPct(row.win_rate, 1)}</td>
                  <td className="py-1.5 pr-3 tabular">{fmt(row.sharpe, 2)}</td>
                  <td className="py-1.5 pr-3 tabular">{fmtPct(row.total_return, 1)}</td>
                  <td className="py-1.5 pr-3 tabular">{fmtPct(row.max_drawdown, 1)}</td>
                  <td className="py-1.5 pr-3 tabular">{row.trade_count ?? "—"}</td>
                  <td className="py-1.5 pr-3 tabular">{fmt(row.score, 3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Decision */}
      <section className="td-panel">
        <h2 className="mb-3 text-[14px] font-medium" style={{ color: "var(--td-ink-100)" }}>
          Decision
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Confidence state" value={decision.confidence_state || "—"} emphasize />
          <Stat label="Vehicle" value={decision.vehicle || "—"} emphasize />
          <Stat label="Risk %" value={fmtPct(decision.risk_pct, 2)} emphasize />
          <Stat label="Conviction" value={fmt(decision.conviction, 4)} emphasize />
        </div>
        {decision.reasons && decision.reasons.length > 0 ? (
          <div className="mt-3">
            <span className="td-label">Reasons</span>
            <ul className="mt-1 flex flex-col gap-1">
              {decision.reasons.map((r, i) => (
                <li
                  key={`reason-${i}`}
                  className="text-[13px] leading-snug"
                  style={{ color: "var(--td-ink-300)" }}
                >
                  {r}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      {/* Suggestion */}
      <section className="td-panel">
        <h2 className="mb-3 text-[14px] font-medium" style={{ color: "var(--td-ink-100)" }}>
          Suggestion
        </h2>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <ActionChip action={ticket.action || "WAIT"} size="md" />
          <span
            className="text-[12px]"
            style={{ fontFamily: "var(--td-font-mono)", color: "var(--td-ink-400)" }}
          >
            {ticket.mode} · {ticket.vehicle}
          </span>
        </div>
        <ol className="flex flex-col gap-1.5 list-none p-0">
          {ticket.steps && ticket.steps.length > 0 ? (
            ticket.steps.map((s, i) => (
              <li
                key={`step-${i}`}
                className="flex gap-2 text-[13px] leading-snug"
                style={{ color: "var(--td-ink-200)" }}
              >
                <span
                  className="tabular shrink-0"
                  style={{ fontFamily: "var(--td-font-mono)", color: "var(--td-ink-500)" }}
                >
                  {i + 1}.
                </span>
                <span>{s}</span>
              </li>
            ))
          ) : (
            <li className="text-[13px]" style={{ color: "var(--td-ink-400)" }}>
              No explicit steps.
            </li>
          )}
        </ol>

        {suggestion.options ? (
          <div className="mt-3">
            <span className="td-label">Options structure</span>
            <p className="text-[13px]" style={{ color: "var(--td-ink-300)" }}>
              {suggestion.options.action === "buy"
                ? `${suggestion.options.structure} ${symbol} exp ${suggestion.options.expiry} — ` +
                  `long ${suggestion.options.long_strike} / short ${suggestion.options.short_strike} — ` +
                  `debit $${fmt(suggestion.options.debit_per_share, 2)}`
                : suggestion.options.reason || "No options structure"}
            </p>
          </div>
        ) : null}
      </section>

      {/* Drivers */}
      <section className="td-panel">
        <h2 className="mb-3 text-[14px] font-medium" style={{ color: "var(--td-ink-100)" }}>
          Drivers
        </h2>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {suggestion.drivers.map((d, i) => (
            <div
              key={`driver-${i}`}
              className="flex items-center justify-between gap-2 p-2"
              style={{ border: "1px solid var(--td-hairline)" }}
            >
              <span className="text-[12px]" style={{ color: "var(--td-ink-200)" }}>
                {d.name}
              </span>
              <span
                className="text-[12px] tabular"
                style={{ fontFamily: "var(--td-font-mono)", color: driverLabelColor(d.impact) }}
              >
                {d.value}
              </span>
              <span
                className="text-[10px] tabular uppercase"
                style={{ fontFamily: "var(--td-font-mono)", color: impactColor(d.impact) }}
              >
                {d.impact}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* Alternatives */}
      <section className="td-panel">
        <h2 className="mb-2 text-[14px] font-medium" style={{ color: "var(--td-ink-100)" }}>
          What would change this
        </h2>
        <ul className="flex flex-col gap-1">
          {suggestion.alternatives.map((a, i) => (
            <li
              key={`alt-${i}`}
              className="text-[13px] leading-snug"
              style={{ color: "var(--td-ink-300)" }}
            >
              {a}
            </li>
          ))}
        </ul>
      </section>

      <ModelFlow className="mt-2" />
    </div>
  );
}
