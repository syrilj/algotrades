"use client";

import type {
  AnalyzeState,
  ModelSelection,
  PlainPlan,
  PositionSize,
} from "@/lib/types";
import { ActionChip, actionStyle } from "@/components/ui/ActionChip";
import { ConfidenceMeter } from "@/components/ui/ConfidenceMeter";

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

function fmtPct(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(0)}%`;
}

type VerdictPanelProps = {
  symbol?: string;
  state: AnalyzeState | null;
  plan?: PlainPlan | null;
  size?: PositionSize | null;
  model?: string;
  selection?: ModelSelection | null;
  empty?: boolean;
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
        className="flex h-full min-h-[200px] flex-col justify-center gap-2 p-4"
        style={{
          borderLeft: "2px solid var(--td-ink-600)",
          background: "var(--td-ink-900)",
        }}
        aria-label="Verdict"
      >
        <p
          className="text-[12px]"
          style={{ color: "var(--td-ink-400)" }}
        >
          Run a symbol to see action, levels, and size.
        </p>
      </aside>
    );
  }

  const rail = actionStyle(plan.action);
  const sym = symbol ?? state.symbol;

  return (
    <aside
      className="flex h-full flex-col gap-4 p-4"
      style={{
        borderLeft: `2px solid ${rail.color}`,
        background: "var(--td-ink-900)",
      }}
      aria-label="Verdict"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span
          className="text-[28px] font-medium leading-none"
          style={{
            fontFamily: "var(--td-font-display)",
            color: "var(--td-ink-50)",
          }}
        >
          {sym}
        </span>
        <ActionChip action={plan.action} size="lg" />
      </div>

      <div className="flex flex-col gap-2">
        <div>
          <span className="td-label">Why</span>
          <p className="text-[13px] leading-snug" style={{ color: "var(--td-ink-200)" }}>
            {plan.why}
          </p>
        </div>
        <div>
          <span className="td-label">Do next</span>
          <p className="text-[13px] leading-snug" style={{ color: "var(--td-ink-200)" }}>
            {plan.do_next}
          </p>
        </div>
      </div>

      <ConfidenceMeter value={state.confidence ?? 0} />
      {plan.confidence_note ? (
        <p className="text-[11px]" style={{ color: "var(--td-ink-400)" }}>
          {plan.confidence_note}
        </p>
      ) : null}

      <div className="grid grid-cols-2 gap-x-4 gap-y-2">
        <Stat label="Hit chance" value={fmtPct(state.hit_probability)} />
        <Stat label="Price" value={fmt(state.price)} />
        <Stat label="Entry" value={fmt(state.entry)} />
        <Stat label="Stop" value={fmt(state.stop)} />
        <Stat label="Trail arm" value={fmt(state.trail_arm)} />
        <Stat label="Risk / sh" value={fmt(state.risk_per_share)} />
      </div>

      {size ? (
        <div
          className="grid grid-cols-2 gap-x-4 gap-y-2 border-t pt-3"
          style={{ borderColor: "var(--td-ink-700)" }}
        >
          <Stat label="Shares" value={String(size.shares)} />
          <Stat label="Notional" value={fmtUsd(size.notional)} />
          <Stat label="$ risk" value={fmtUsd(size.dollar_risk)} />
          <Stat label="Risk %" value={`${fmt(size.risk_pct, 2)}%`} />
          <Stat label="Account" value={fmtUsd(size.account)} />
          {size.rr_to_arm != null ? (
            <Stat label="R:R arm" value={fmt(size.rr_to_arm, 2)} />
          ) : null}
        </div>
      ) : null}

      <div
        className="mt-auto flex flex-col gap-0.5 border-t pt-3 text-[11px]"
        style={{ borderColor: "var(--td-ink-700)", color: "var(--td-ink-400)" }}
      >
        <span style={{ fontFamily: "var(--td-font-mono)", color: "var(--td-ink-200)" }}>
          {model ?? state.model}
        </span>
        {selection?.reason ? <span>{selection.reason}</span> : null}
        <span>asof {state.asof ?? "—"}</span>
      </div>
    </aside>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="td-label mb-0">{label}</div>
      <div
        className="tabular text-[13px]"
        style={{ fontFamily: "var(--td-font-mono)", color: "var(--td-ink-100)" }}
      >
        {value}
      </div>
    </div>
  );
}
