"use client";

import Link from "next/link";
import type {
  AnalyzeState,
  ModelSelection,
  PlainPlan,
  PositionSize,
} from "@/lib/types";
import { ActionChip, actionStyle } from "@/components/ui/ActionChip";
import { ConfidenceMeter } from "@/components/ui/ConfidenceMeter";
import { Stat } from "@/components/ui/Stat";
import { TradeButton } from "@/components/analyze/TradeButton";
import { gammaHref, liveHref, optionsHref } from "@/lib/routes";
import { formatPct } from "@/lib/format";
import {
  CheckCircle2,
  XCircle,
  Info,
  TrendingUp,
  Activity,
  Layers,
  Award,
  Shield,
  HelpCircle,
} from "lucide-react";

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

function buildOperatorSteps(
  state: AnalyzeState,
  plan: PlainPlan,
  size: PositionSize | null | undefined,
): string[] {
  const action = (plan.action ?? "").toUpperCase();
  const steps: string[] = [];

  if (action.includes("AVOID") || action === "WAIT") {
    steps.push(plan.do_next || "Stand aside — no edge on this print.");
    if (state.stop != null) {
      steps.push(`Invalidation / structure break near ${fmt(state.stop)}.`);
    }
    steps.push("Re-check after next bar or open Live for risk mode.");
    return steps;
  }

  if (action.includes("WAIT") || action.includes("WATCH") || action.includes("PULLBACK")) {
    steps.push(plan.do_next || "Wait for trigger — do not chase.");
    if (state.entry != null) {
      steps.push(`Trigger / entry zone ≈ ${fmt(state.entry)}.`);
    }
    if (state.stop != null) {
      steps.push(`Hard stop if triggered: ${fmt(state.stop)}.`);
    }
    if (size && size.shares > 0) {
      steps.push(
        `Pre-size: ${size.shares} sh · risk ${fmtUsd(size.dollar_risk)} (${formatPct(size.risk_pct, 2)}).`,
      );
    }
    return steps;
  }

  // BUY paths
  steps.push(plan.do_next || "Execute only if levels still valid.");
  if (state.entry != null) {
    steps.push(`Entry near ${fmt(state.entry)} (spot ${fmt(state.price)}).`);
  }
  if (state.stop != null) {
    steps.push(`Stop ${fmt(state.stop)} · trail arm ${fmt(state.trail_arm)}.`);
  }
  if (size && size.shares > 0) {
    steps.push(
      `Size ${size.shares} sh · notional ${fmtUsd(size.notional)} · $ risk ${fmtUsd(size.dollar_risk)}.`,
    );
  } else {
    steps.push("Size not available — set account / risk and re-run.");
  }
  steps.push("Open Live for vehicle (equity vs options) · Options for structure.");
  return steps;
}

type VerdictPanelProps = {
  symbol?: string;
  state: AnalyzeState | null;
  plan?: PlainPlan | null;
  size?: PositionSize | null;
  model?: string;
  selection?: ModelSelection | null;
  empty?: boolean;
  compact?: boolean;
};

export function VerdictPanel({
  symbol,
  state,
  plan,
  size,
  model,
  selection,
  empty,
}: VerdictPanelProps) {
  if (empty || !state || !plan) {
    return (
      <aside
        className="td-panel td-ticket td-ticket--empty flex flex-col gap-4 p-6"
        style={{ background: "var(--td-surface-card)", borderColor: "var(--td-hairline)" }}
        aria-label="Verdict"
      >
        <div className="flex items-center gap-2 border-b border-[var(--td-hairline)] pb-3">
          <HelpCircle className="w-5 h-5 text-[var(--td-ink-400)]" />
          <p className="text-md font-semibold text-[var(--td-ink)]">
            No ticket generated yet
          </p>
        </div>
        <ol
          className="flex flex-col gap-2 text-[13px]"
          style={{ color: "var(--td-ink-300)" }}
        >
          <li className="flex gap-2">
            <span className="font-mono text-[var(--td-ink-500)]">1.</span>
            <span>Enter a ticker above and select a model, then press Run</span>
          </li>
          <li className="flex gap-2">
            <span className="font-mono text-[var(--td-ink-500)]">2.</span>
            <span>Evaluate action recommendation, execution steps, and optimal size</span>
          </li>
          <li className="flex gap-2">
            <span className="font-mono text-[var(--td-ink-500)]">3.</span>
            <span>Route directly to Live risk desk or Options spread selector</span>
          </li>
        </ol>
        <p className="text-[12px] italic" style={{ color: "var(--td-ink-500)" }}>
          Tip: You can click any winner bag asset on the landing page to auto-run a routed plan.
        </p>
      </aside>
    );
  }

  const rail = actionStyle(plan.action);
  const sym = symbol ?? state.symbol;
  const steps = buildOperatorSteps(state, plan, size);

  return (
    <aside
      className="td-panel td-ticket relative overflow-hidden flex flex-col gap-4 rounded-xl border"
      style={{
        background: "var(--td-surface-card)",
        borderColor: "var(--td-hairline)",
        borderLeft: `4px solid ${rail.color}`,
        padding: "1.5rem",
        boxShadow: "0 4px 20px rgba(0,0,0,0.15)",
      }}
      aria-label="Verdict"
    >
      {/* Header Row */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[var(--td-hairline)] pb-4">
        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-mono uppercase tracking-wider text-[var(--td-muted)] flex items-center gap-1.5">
            <Shield className="w-3.5 h-3.5" style={{ color: rail.color }} />
            Operator Trade Ticket
          </span>
          <div className="flex flex-wrap items-baseline gap-3">
            <span className="td-ticker" style={{ fontSize: "1.75rem", fontWeight: 800 }}>{sym}</span>
            <span className="td-ticker-price text-lg font-mono font-bold text-[var(--td-ink)]">{fmtUsd(state.price)}</span>
            <span className="text-xs font-mono text-[var(--td-ink-400)] bg-[var(--td-surface-elevated)] px-2 py-0.5 rounded">
              {model ?? state.model}
            </span>
          </div>
          {selection?.reason ? (
            <p className="text-[11px] text-[var(--td-muted)] flex items-center gap-1 mt-0.5">
              <Award className="w-3 h-3 text-[var(--td-brand)] shrink-0" />
              <span>{selection.reason}</span>
            </p>
          ) : null}
        </div>
        <ActionChip action={plan.action} size="lg" />
      </div>

      {/* Recommended Action Hero Banner */}
      <div className="p-4 rounded-lg bg-[var(--td-surface-elevated)] border-l-2" style={{ borderColor: rail.color }}>
        <span className="text-[10px] font-mono uppercase tracking-wider text-[var(--td-muted)] block mb-1">Recommended Action</span>
        <p className="text-sm font-semibold text-[var(--td-ink-100)] leading-relaxed uppercase">{plan.do_next || plan.why}</p>
      </div>

      {/* Two-Column Structured Split */}
      <div className="flex flex-col lg:flex-row gap-6 w-full">
        {/* Left Column: Core Trade Parameters & Execution */}
        <div className="flex-1 flex flex-col gap-4">
          <div>
            <span className="td-label text-xs uppercase tracking-wider text-[var(--td-muted)] mb-2 block">Position Sizing & Levels</span>
            <div className="grid grid-cols-2 gap-3 p-3 rounded-lg border border-[var(--td-hairline)] bg-[var(--td-surface-soft)]">
              <Stat label="Entry Target" value={state.entry != null ? fmtUsd(state.entry) : "Market"} emphasize />
              <Stat label="Stop Loss" value={state.stop != null ? fmtUsd(state.stop) : "—"} emphasize />
              <Stat label="Shares Size" value={size ? String(size.shares) : "—"} emphasize />
              <Stat label="Dollar Risk" value={size ? fmtUsd(size.dollar_risk) : "—"} emphasize />
            </div>
          </div>

          {size && size.shares > 0 ? (
            <div className="grid grid-cols-3 gap-2 text-center text-xs p-2.5 rounded border border-[var(--td-hairline)] bg-[var(--td-surface-soft)]/50 font-mono">
              <div>
                <span className="text-[10px] text-[var(--td-muted)] block">Notional</span>
                <span className="font-semibold text-[var(--td-ink)]">{fmtUsd(size.notional)}</span>
              </div>
              <div>
                <span className="text-[10px] text-[var(--td-muted)] block">Risk %</span>
                <span className="font-semibold text-[var(--td-ink)]">{formatPct(size.risk_pct, 2)}</span>
              </div>
              <div>
                <span className="text-[10px] text-[var(--td-muted)] block">Account</span>
                <span className="font-semibold text-[var(--td-ink)]">{fmtUsd(size.account)}</span>
              </div>
            </div>
          ) : null}

          {/* Action Buttons */}
          <div className="flex flex-col gap-2 mt-2">
            {state && plan && model ? (
              <TradeButton
                symbol={sym}
                state={state}
                plan={plan}
                size={size}
                model={model ?? state.model}
                reason={selection?.reason}
              />
            ) : null}
            <div className="grid grid-cols-3 gap-2">
              <Link href={liveHref(sym)} className="td-btn td-btn-primary flex items-center justify-center gap-1.5 text-xs py-2 no-underline">
                <Activity className="w-3.5 h-3.5" />
                Live Risk
              </Link>
              <Link href={optionsHref(sym)} className="td-btn td-btn-ghost flex items-center justify-center gap-1.5 text-xs py-2 no-underline">
                <Layers className="w-3.5 h-3.5" />
                Options
              </Link>
              <Link href={gammaHref(sym)} className="td-btn td-btn-ghost flex items-center justify-center gap-1.5 text-xs py-2 no-underline">
                <TrendingUp className="w-3.5 h-3.5" />
                Gamma
              </Link>
            </div>
          </div>
        </div>

        {/* Right Column: Confidence Reasoning & Checklist */}
        <div className="flex-1 flex flex-col gap-4 border-t lg:border-t-0 lg:border-l border-[var(--td-hairline)] pt-4 lg:pt-0 lg:pl-6">
          <div className="flex flex-col gap-3">
            <ConfidenceMeter
              value={state.confidence ?? 0}
              label="Structure Readiness"
            />

            <div className="grid grid-cols-2 gap-2 mt-1">
              <div className="p-2 rounded bg-[var(--td-surface-soft)] border border-[var(--td-hairline)]">
                <span className="text-[10px] text-[var(--td-muted)] block">Hit Probability</span>
                <span className="text-sm font-mono font-bold text-[var(--td-ink)]">{formatPct(state.hit_probability, 0)}</span>
              </div>
              <div className="p-2 rounded bg-[var(--td-surface-soft)] border border-[var(--td-hairline)]">
                <span className="text-[10px] text-[var(--td-muted)] block">RVOL Ratio</span>
                <span className="text-sm font-mono font-bold text-[var(--td-ink)]">
                  {state.rvol != null
                    ? `${state.rvol.toFixed(1)}x${state.vol_dry ? " dry" : state.vol_surge ? " ↑" : ""}`
                    : "—"}
                </span>
              </div>
            </div>

            {state.confidence_source ? (
              <div className="text-[10px] text-[var(--td-muted)] font-mono flex items-center gap-1.5 bg-[var(--td-surface-soft)] p-2 rounded border border-[var(--td-hairline)]">
                <Info className="w-3.5 h-3.5 text-[var(--td-brand)] shrink-0" />
                <span>Source: {String(state.confidence_source).replace(/_/g, " ")}</span>
              </div>
            ) : null}
          </div>

          {/* Checklist of Gates */}
          {plan.checklist && plan.checklist.length > 0 ? (
            <div>
              <span className="td-label text-xs uppercase tracking-wider text-[var(--td-muted)] mb-2 block">Structural Gate Checklist</span>
              <div className="flex flex-col gap-2 max-h-[160px] overflow-y-auto pr-1 border border-[var(--td-hairline)] rounded-lg p-2.5 bg-[var(--td-surface-soft)]">
                {plan.checklist.map((item) => (
                  <div key={item.key} className="flex items-start gap-2 text-xs">
                    {item.ok ? (
                      <CheckCircle2 className="w-4 h-4 text-[var(--td-action-buy-now)] shrink-0 mt-0.5" />
                    ) : (
                      <XCircle className="w-4 h-4 text-[var(--td-action-avoid)] shrink-0 mt-0.5" />
                    )}
                    <span className={item.ok ? "text-[var(--td-ink-200)]" : "text-[var(--td-ink-400)]"}>
                      {item.label}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {/* Collapsible Lower Section for Explanation & Steps */}
      <div className="border-t border-[var(--td-hairline)] pt-4 mt-2">
        <details className="td-details border border-[var(--td-hairline)] rounded-lg bg-[var(--td-surface-soft)]" open={false}>
          <summary className="td-details__summary font-mono text-[10px] font-bold text-[var(--td-ink-300)] hover:text-[var(--td-ink)] select-none">
            Why · Steps · System Details
          </summary>
          <div className="mt-4 flex flex-col gap-4 text-xs">
            <div>
              <span className="text-[10px] font-mono uppercase tracking-wider text-[var(--td-muted)] block mb-1.5">Execution Steps</span>
              <ol className="flex flex-col gap-2 p-0 list-none m-0">
                {steps.map((s, i) => (
                  <li key={i} className="flex gap-2.5 items-start text-[var(--td-ink-200)] bg-[var(--td-surface-card)] p-2.5 rounded border border-[var(--td-hairline)]">
                    <span className="w-5 h-5 rounded-full bg-[var(--td-surface-elevated)] flex items-center justify-center font-mono font-bold text-[10px] text-[var(--td-muted)] shrink-0 border border-[var(--td-hairline)]">
                      {i + 1}
                    </span>
                    <span className="leading-normal">{s}</span>
                  </li>
                ))}
              </ol>
            </div>

            <div>
              <span className="text-[10px] font-mono uppercase tracking-wider text-[var(--td-muted)] block mb-1.5">Stance Analysis</span>
              <p className="text-[var(--td-ink-200)] leading-relaxed bg-[var(--td-surface-card)] p-2.5 rounded border border-[var(--td-hairline)] m-0">{plan.why}</p>
            </div>

            {plan.confidence_note ? (
              <div>
                <span className="text-[10px] font-mono uppercase tracking-wider text-[var(--td-muted)] block mb-1.5">Confidence Note</span>
                <p className="p-2.5 rounded bg-[var(--td-surface-card)] border border-[var(--td-hairline)] font-mono text-[10px] text-[var(--td-muted)] m-0">
                  {plan.confidence_note}
                </p>
              </div>
            ) : null}

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 font-mono text-[10px] text-[var(--td-muted)] border-t border-[var(--td-hairline)] pt-3">
              <div>Trail arm: <span className="text-[var(--td-ink-200)] font-semibold">${fmt(state.trail_arm)}</span></div>
              <div>Risk / sh: <span className="text-[var(--td-ink-200)] font-semibold">${fmt(state.risk_per_share)}</span></div>
              {state.asof ? <div>asof: <span className="text-[var(--td-ink-200)] font-semibold">{state.asof}</span></div> : null}
            </div>
          </div>
        </details>
      </div>
    </aside>
  );
}
