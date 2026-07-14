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
import { TradeButton } from "@/components/analyze/TradeButton";
import { gammaHref, liveHref, optionsHref } from "@/lib/routes";
import { formatPct } from "@/lib/format";

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
        className="td-panel td-ticket td-ticket--empty"
        style={{ borderLeft: "3px solid var(--td-ink-600)" }}
        aria-label="Verdict"
      >
        <p className="td-ticker" style={{ fontSize: "1.15rem" }}>
          No ticket yet
        </p>
        <ol
          className="flex flex-col gap-1.5 text-[13px]"
          style={{ color: "var(--td-ink-300)" }}
        >
          <li>1. Enter a ticker above and press Run</li>
          <li>2. Read action → do next → size</li>
          <li>3. Route to Live (risk) or Options (structure)</li>
        </ol>
        <p className="text-[12px]" style={{ color: "var(--td-ink-500)" }}>
          Or open a name from Watch / Picks — deep-links auto-run.
        </p>
      </aside>
    );
  }

  const rail = actionStyle(plan.action);
  const sym = symbol ?? state.symbol;
  const steps = buildOperatorSteps(state, plan, size);

  return (
    <aside
      className="td-panel td-ticket"
      style={{
        borderLeft: `3px solid ${rail.color}`,
        background: `color-mix(in oklch, ${rail.color} 7%, var(--td-ink-900))`,
      }}
      aria-label="Verdict"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <span className="td-label">Operator ticket</span>
          <div className="flex flex-wrap items-baseline gap-3">
            <span className="td-ticker">{sym}</span>
            <span className="td-ticker-price">{fmt(state.price)}</span>
          </div>
        </div>
        <ActionChip action={plan.action} size="lg" />
      </div>

      <div>
        <span className="td-label">Do this</span>
        <p className="td-do-next">{plan.do_next}</p>
      </div>

      <div>
        <span className="td-label">Steps</span>
        <ol className="mt-1 flex flex-col gap-1.5">
          {steps.map((s, i) => (
            <li
              key={`${i}-${s.slice(0, 24)}`}
              className="flex gap-2 text-[13px] leading-snug"
              style={{ color: "var(--td-ink-200)" }}
            >
              <span
                className="tabular shrink-0"
                style={{
                  fontFamily: "var(--td-font-mono)",
                  color: "var(--td-ink-500)",
                }}
              >
                {i + 1}.
              </span>
              <span>{s}</span>
            </li>
          ))}
        </ol>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
        <Stat label="Entry" value={fmt(state.entry)} emphasize />
        <Stat label="Stop" value={fmt(state.stop)} emphasize />
        <Stat label="Shares" value={size ? String(size.shares) : "—"} emphasize />
        <Stat label="$ risk" value={size ? fmtUsd(size.dollar_risk) : "—"} emphasize />
      </div>

      <div className="flex flex-wrap gap-2">
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
        <Link href={liveHref(sym)} className="td-btn td-btn-primary no-underline">
          Open Live
        </Link>
        <Link href={optionsHref(sym)} className="td-btn td-btn-ghost no-underline">
          Options structure
        </Link>
        <Link href={gammaHref(sym)} className="td-btn td-btn-ghost no-underline">
          Gamma
        </Link>
      </div>

      <ConfidenceMeter value={state.confidence ?? 0} />

      <details className="td-details">
        <summary className="td-details__summary">Why · levels · model</summary>
        <div className="mt-3 flex flex-col gap-3">
          <div>
            <span className="td-label">Why</span>
            <p className="text-[13px] leading-snug" style={{ color: "var(--td-ink-300)" }}>
              {plan.why}
            </p>
            {plan.confidence_note ? (
              <p className="mt-1 text-[11px]" style={{ color: "var(--td-ink-500)" }}>
                {plan.confidence_note}
              </p>
            ) : null}
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
            <Stat label="Hit chance" value={formatPct(state.hit_probability, 0)} />
            <Stat label="Trail arm" value={fmt(state.trail_arm)} />
            <Stat label="Risk / sh" value={fmt(state.risk_per_share)} />
            {size ? (
              <>
                <Stat label="Notional" value={fmtUsd(size.notional)} />
                <Stat label="Risk %" value={formatPct(size.risk_pct, 2)} />
                <Stat label="Account" value={fmtUsd(size.account)} />
              </>
            ) : null}
          </div>
          <div
            className="flex flex-col gap-0.5 border-t pt-3 text-[11px]"
            style={{ borderColor: "var(--td-ink-700)", color: "var(--td-ink-400)" }}
          >
            <span
              style={{ fontFamily: "var(--td-font-mono)", color: "var(--td-ink-200)" }}
            >
              {model ?? state.model}
            </span>
            {selection?.source === "symbol_ranker" ? (
              <span className="td-chip text-[10px]" style={{ alignSelf: "flex-start" }}>
                via ranker
              </span>
            ) : null}
            {selection?.reason ? <span>{selection.reason}</span> : null}
            <span>asof {state.asof ?? "—"}</span>
          </div>
        </div>
      </details>
    </aside>
  );
}

function Stat({
  label,
  value,
  emphasize,
}: {
  label: string;
  value: string;
  emphasize?: boolean;
}) {
  return (
    <div>
      <div className="td-label mb-0">{label}</div>
      <div
        className="tabular"
        style={{
          fontFamily: "var(--td-font-mono)",
          color: emphasize ? "var(--td-ink-50)" : "var(--td-ink-100)",
          fontSize: emphasize ? "15px" : "13px",
          fontWeight: emphasize ? 600 : 400,
        }}
      >
        {value}
      </div>
    </div>
  );
}
