"use client";

import {
  Activity,
  BrainCircuit,
  CandlestickChart,
  Filter,
  GitBranch,
  Layers,
  Scale,
  Target,
  type LucideIcon,
} from "lucide-react";
import type { AnalyzeState, PlainPlan, PositionSize } from "@/lib/types";
import { ActionChip } from "@/components/ui/ActionChip";

export type PipelinePhase = "idle" | "running" | "done" | "error";
export type StageStatus = "idle" | "running" | "pass" | "fail" | "neutral";

type StageDef = {
  id: string;
  label: string;
  group: string;
  hint: string;
  Icon: LucideIcon;
  status: StageStatus;
  value?: string;
};

function fmt(n: number | null | undefined, digits = 2): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return n.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function filterOk(flags: AnalyzeState["flags"]): boolean | null {
  if (!flags) return null;
  const keys = [
    "vwap_uptrend",
    "above_vwap",
    "vol_confirm_or_pull",
    "not_red_flag",
    "sqz_off_or_release",
  ] as const;
  const present = keys.filter((key) => flags[key] !== undefined);
  if (present.length === 0) return null;
  return present.every((key) => flags[key] === true);
}

function statusFrom(
  phase: PipelinePhase,
  index: number,
  activeStage: number,
  ok: boolean | null,
): StageStatus {
  if (phase === "idle") return "idle";
  if (phase === "running") {
    // The API resolves as one completed result. Do not pretend we know which
    // internal stage is currently executing until real event telemetry exists.
    if (activeStage < 0) return "idle";
    if (index < activeStage) return ok === false ? "fail" : ok === true ? "pass" : "neutral";
    return index === activeStage ? "running" : "idle";
  }
  if (phase === "error" && index === 7) return "fail";
  return ok === false ? "fail" : ok === true ? "pass" : "neutral";
}

function buildStages(
  state: AnalyzeState | null,
  plan: PlainPlan | null | undefined,
  size: PositionSize | null | undefined,
  phase: PipelinePhase,
  activeStage: number,
): StageDef[] {
  const flags = state?.flags;
  const filters = filterOk(flags);
  const hasMeta = state?.hit_probability != null;
  const defs: Array<Omit<StageDef, "status"> & { ok: boolean | null }> = [
    { id: "ohlcv", label: "Market feed", group: "01 / INGEST", hint: "price, volume & timestamp", Icon: CandlestickChart, ok: state?.price != null ? true : phase === "done" ? false : null, value: state ? `${fmt(state.price)} · ${state.asof ?? "—"}` : undefined },
    { id: "va", label: "Auction map", group: "02 / CONTEXT", hint: "POC · value area", Icon: Layers, ok: state?.poc != null && state?.val != null && state?.vah != null ? true : phase === "done" ? false : null, value: state ? `POC ${fmt(state.poc)} · VAL ${fmt(state.val)} · VAH ${fmt(state.vah)}` : undefined },
    { id: "htf", label: "Trend field", group: "02 / CONTEXT", hint: "higher-timeframe bias", Icon: Activity, ok: flags?.htf_ha_green !== undefined ? !!flags.htf_ha_green : null, value: flags?.htf_ha_green === undefined ? undefined : flags.htf_ha_green ? "trend aligned" : "trend opposed" },
    { id: "rule", label: "Setup rule", group: "03 / SIGNAL", hint: "pattern qualification", Icon: GitBranch, ok: state?.setup_ok !== undefined ? !!state.setup_ok : state?.setup_kind ? true : null, value: state?.setup_kind ?? undefined },
    { id: "filters", label: "Safety gates", group: "03 / SIGNAL", hint: "VWAP · volume · squeeze", Icon: Filter, ok: filters, value: filters === null ? undefined : filters ? "all gates clear" : "one or more gates blocked" },
    { id: "risk", label: "Risk engine", group: "04 / RISK", hint: "exposure & conviction", Icon: Scale, ok: state?.sleeve_fraction != null || state?.confidence != null ? true : null, value: state ? `sleeve ${fmt((state.sleeve_fraction ?? 0) * 100, 0)}% · confidence ${fmt((state.confidence ?? 0) * 100, 0)}%` : undefined },
    { id: "meta", label: "Meta model", group: "04 / RISK", hint: "probability calibration", Icon: BrainCircuit, ok: hasMeta ? true : null, value: hasMeta ? `hit probability ${fmt((state?.hit_probability ?? 0) * 100, 0)}%` : "not used by this model" },
    { id: "action", label: "Decision ticket", group: "05 / OUTPUT", hint: "action · size · next step", Icon: Target, ok: plan?.action ? !String(plan.action).toUpperCase().includes("AVOID") : null, value: plan?.action ? size ? `${plan.action} · ${size.shares} shares` : plan.action : undefined },
  ];

  return defs.map((stage, index) => ({
    ...stage,
    status: statusFrom(phase, index, activeStage, stage.ok),
  }));
}

export function nodeColors(status: StageStatus): { border: string; bg: string; fg: string } {
  switch (status) {
    case "running": return { border: "var(--td-system-active)", bg: "var(--td-system-active-soft)", fg: "var(--td-system-active)" };
    case "pass": return { border: "var(--td-gate-pass)", bg: "color-mix(in srgb, var(--td-gate-pass) 10%, transparent)", fg: "var(--td-gate-pass)" };
    case "fail": return { border: "var(--td-gate-fail)", bg: "color-mix(in srgb, var(--td-gate-fail) 10%, transparent)", fg: "var(--td-gate-fail)" };
    case "neutral": return { border: "var(--td-gate-neutral)", bg: "var(--td-ink-800)", fg: "var(--td-ink-300)" };
    default: return { border: "var(--td-ink-700)", bg: "rgba(10, 16, 24, 0.72)", fg: "var(--td-ink-500)" };
  }
}

type PipelineFlowProps = {
  state: AnalyzeState | null;
  plan?: PlainPlan | null;
  size?: PositionSize | null;
  model?: string;
  phase: PipelinePhase;
  activeStage: number;
};

export function PipelineFlow({ state, plan, size, model, phase, activeStage }: PipelineFlowProps) {
  const stages = buildStages(state, plan, size, phase, activeStage);
  const resolvedStages = stages.filter((stage) => stage.status === "pass" || stage.status === "fail").length;
  const phaseLabel = phase === "running"
    ? "Analysis request in flight"
    : phase === "done"
      ? `${resolvedStages} evidence checks returned`
      : phase === "error"
        ? "Analysis request failed"
        : "The decision path every request follows";

  return (
    <section className="td-pipeline" data-phase={phase} aria-label="Model decision path">
      <div className="td-pipeline__header">
        <div>
          <p className="td-pipeline__kicker">Model flight path</p>
          <h2>From market print to operator decision</h2>
        </div>
        <div className="td-pipeline__telemetry" aria-live="polite">
          <span className={phase === "running" ? "td-pipeline__pulse" : "td-pipeline__status-dot"} aria-hidden />
          <span>{phaseLabel}</span>
          {model ? <code>{model}</code> : null}
        </div>
      </div>

      {phase === "running" ? <p className="td-pipeline__notice">The engine returns one completed decision record, not granular live events. Stage outcomes populate when the response arrives.</p> : null}

      <div className="td-pipeline__map">
        {stages.map((stage, index) => {
          const colors = nodeColors(stage.status);
          const Icon = stage.Icon;
          return (
            <div key={stage.id} className="td-pipeline__segment">
              <div className="td-pipeline__node" style={{ borderColor: colors.border, background: colors.bg, animation: stage.status === "running" ? "td-pipeline-pulse 1.2s var(--td-ease) infinite" : undefined }}>
                <div className="td-pipeline__node-topline">
                  <span>{stage.group}</span>
                  <span className="td-pipeline__node-state" style={{ color: colors.fg }}>
                    {stage.status === "pass" ? "Nominal" : stage.status === "fail" ? "Blocked" : stage.status === "running" ? "Reading" : "Awaiting"}
                  </span>
                </div>
                <div className="td-pipeline__node-title">
                  <Icon size={16} strokeWidth={1.75} style={{ color: colors.fg }} aria-hidden />
                  <span>{stage.label}</span>
                </div>
                {stage.id === "action" && plan?.action && phase === "done" ? <ActionChip action={plan.action} size="sm" /> : stage.value ? <span className="td-pipeline__value" title={stage.value}>{stage.value}</span> : <span className="td-pipeline__hint">{stage.hint}</span>}
              </div>
              {index < stages.length - 1 ? <div className="td-pipeline__connector" aria-hidden><span /></div> : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}
