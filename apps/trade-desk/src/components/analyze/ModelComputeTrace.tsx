"use client";

import { Check, Minus, X } from "lucide-react";
import type {
  AnalyzeState,
  ModelSelection,
  PlainPlan,
  PositionSize,
} from "@/lib/types";
import { formatPct } from "@/lib/format";

function fmt(n: number | null | undefined, digits = 2): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return n.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

type Stage = {
  id: string;
  label: string;
  status: boolean | null;
  value: string;
  meter?: number;
  meterMax?: number;
};

function buildStages(
  state: AnalyzeState,
  plan: PlainPlan | null | undefined,
  size: PositionSize | null | undefined,
): Stage[] {
  const f = state.flags ?? {};
  const filters = [
    f.vwap_uptrend,
    f.above_vwap,
    f.vol_confirm_or_pull,
    f.not_red_flag,
    f.sqz_off_or_release,
  ].filter((v) => v !== undefined);
  const filtersOk =
    filters.length > 0 && filters.every((v) => v === true)
      ? true
      : filters.length > 0
        ? false
        : null;

  return [
    {
      id: "ohlcv",
      label: "OHLCV",
      status: state.price != null ? true : null,
      value: `price ${fmt(state.price)} · ${state.asof ?? "—"}`,
      meter: state.rvol,
      meterMax: 5,
    },
    {
      id: "va",
      label: "VA / POC",
      status:
        state.poc != null && state.val != null && state.vah != null
          ? true
          : null,
      value: `POC ${fmt(state.poc)} · VAL ${fmt(state.val)} · VAH ${fmt(state.vah)}`,
    },
    {
      id: "htf",
      label: "HTF HA",
      status: f.htf_ha_green ?? null,
      value: f.htf_ha_green === true ? "green" : f.htf_ha_green === false ? "not green" : "—",
    },
    {
      id: "rule",
      label: "Rule",
      status: state.setup_ok ?? null,
      value: state.setup_kind ?? "—",
    },
    {
      id: "filters",
      label: "Filters",
      status: filtersOk,
      value: filtersOk === true ? "clear" : filtersOk === false ? "blocked" : "—",
      meter: filtersOk === true ? 1 : filtersOk === false ? 0 : 0,
      meterMax: 1,
    },
    {
      id: "risk",
      label: "Risk / Kelly",
      status:
        state.sleeve_fraction != null && (state.confidence ?? 0) > 0
          ? true
          : null,
      value: `sleeve ${formatPct(state.sleeve_fraction, 0)} · conf ${formatPct(state.confidence, 0)}`,
      meter: state.confidence ?? 0,
      meterMax: 1,
    },
    {
      id: "meta",
      label: "Meta",
      status: state.hit_probability != null ? true : null,
      value: `hit ${formatPct(state.hit_probability, 0)}`,
      meter: state.hit_probability ?? 0,
      meterMax: 1,
    },
    {
      id: "action",
      label: "Action",
      status: plan?.action ? !String(plan.action).toUpperCase().includes("AVOID") : null,
      value: plan?.action ? (size ? `${plan.action} · ${size.shares} sh` : plan.action) : "—",
    },
  ];
}

function StatusIcon({ status }: { status: boolean | null }) {
  if (status === true) return <Check size={12} strokeWidth={1.75} style={{ color: "var(--td-gate-pass)" }} aria-hidden />;
  if (status === false) return <X size={12} strokeWidth={1.75} style={{ color: "var(--td-gate-fail)" }} aria-hidden />;
  return <Minus size={12} strokeWidth={1.75} style={{ color: "var(--td-gate-neutral)" }} aria-hidden />;
}

function TraceBar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.min(100, (Math.max(0, value) / max) * 100) : 0;
  return (
    <div
      className="h-1.5 w-16 overflow-hidden rounded-sm"
      style={{ background: "var(--td-ink-700)" }}
    >
      <div
        className="h-full rounded-sm"
        style={{ width: `${pct}%`, background: "var(--td-brand)" }}
      />
    </div>
  );
}

type ModelComputeTraceProps = {
  state: AnalyzeState | null;
  plan?: PlainPlan | null;
  size?: PositionSize | null;
  model?: string;
  selection?: ModelSelection | null;
};

export function ModelComputeTrace({
  state,
  plan,
  size,
  model,
  selection,
}: ModelComputeTraceProps) {
  if (!state) {
    return (
      <section className="td-panel p-3" aria-label="Compute trace">
        <p className="text-[13px]" style={{ color: "var(--td-ink-400)" }}>
          Run analyze to see the model compute trace.
        </p>
      </section>
    );
  }

  const stages = buildStages(state, plan, size);
  const activeModel = model ?? state.model;

  return (
    <section className="td-panel p-3" aria-label="Compute trace">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h2
          className="text-[16px] font-medium"
          style={{ color: "var(--td-ink-100)" }}
        >
          Compute trace
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          {activeModel ? (
            <span
              className="text-[11px]"
              style={{ fontFamily: "var(--td-font-mono)", color: "var(--td-ink-300)" }}
            >
              {activeModel}
            </span>
          ) : null}
          {selection?.source === "symbol_ranker" ? (
            <span
              className="text-[10px]"
              style={{ color: "var(--td-ink-400)" }}
            >
              via ranker
            </span>
          ) : null}
          {selection?.reason ? (
            <span
              className="text-[10px]"
              style={{ color: "var(--td-ink-400)" }}
              title={selection.reason}
            >
              {selection.reason}
            </span>
          ) : null}
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        {stages.map((stage, i) => (
          <div
            key={stage.id}
            className="flex items-center gap-3 py-1.5 text-[12px]"
            style={{ borderBottom: i < stages.length - 1 ? "1px solid var(--td-ink-700)" : undefined }}
          >
            <span
              className="tabular w-4 shrink-0 text-center"
              style={{ fontFamily: "var(--td-font-mono)", color: "var(--td-ink-500)" }}
            >
              {i + 1}
            </span>
            <StatusIcon status={stage.status} />
            <span
              className="w-24 shrink-0 font-medium"
              style={{ color: "var(--td-ink-200)" }}
            >
              {stage.label}
            </span>
            <span
              className="min-w-0 flex-1 truncate"
              style={{ fontFamily: "var(--td-font-mono)", color: "var(--td-ink-300)" }}
              title={stage.value}
            >
              {stage.value}
            </span>
            {stage.meter != null && stage.meterMax != null ? (
              <TraceBar value={stage.meter} max={stage.meterMax} />
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
}
