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
  const present = keys.filter((k) => flags[k] !== undefined);
  if (present.length === 0) return null;
  return present.every((k) => flags[k] === true);
}

function statusFrom(
  phase: PipelinePhase,
  index: number,
  activeStage: number,
  ok: boolean | null,
): StageStatus {
  if (phase === "idle") return "idle";
  if (phase === "running") {
    if (index < activeStage) {
      if (ok === false) return "fail";
      if (ok === true) return "pass";
      return "neutral";
    }
    if (index === activeStage) return "running";
    return "idle";
  }
  if (phase === "error" && index === 7) return "fail";
  if (ok === false) return "fail";
  if (ok === true) return "pass";
  return "neutral";
}

function buildStages(
  state: AnalyzeState | null,
  plan: PlainPlan | null | undefined,
  size: PositionSize | null | undefined,
  model: string | undefined,
  phase: PipelinePhase,
  activeStage: number,
): StageDef[] {
  const flags = state?.flags;
  const hasMeta = state?.hit_probability != null;
  const filters = filterOk(flags);

  const defs: Array<{
    id: string;
    label: string;
    Icon: LucideIcon;
    ok: boolean | null;
    value?: string;
  }> = [
    {
      id: "ohlcv",
      label: "OHLCV",
      Icon: CandlestickChart,
      ok: state?.price != null ? true : phase === "done" ? false : null,
      value: state ? `${fmt(state.price)} · ${state.asof ?? "—"}` : undefined,
    },
    {
      id: "va",
      label: "VA / POC",
      Icon: Layers,
      ok:
        state?.poc != null && state?.val != null && state?.vah != null
          ? true
          : phase === "done"
            ? false
            : null,
      value: state
        ? `POC ${fmt(state.poc)} · VAL ${fmt(state.val)} · VAH ${fmt(state.vah)}`
        : undefined,
    },
    {
      id: "htf",
      label: "HTF HA",
      Icon: Activity,
      ok:
        flags?.htf_ha_green !== undefined
          ? !!flags.htf_ha_green
          : phase === "done"
            ? null
            : null,
      value:
        flags?.htf_ha_green === undefined
          ? undefined
          : flags.htf_ha_green
            ? "green"
            : "not green",
    },
    {
      id: "rule",
      label: "Rule",
      Icon: GitBranch,
      ok:
        state?.setup_ok !== undefined
          ? !!state.setup_ok
          : state?.setup_kind
            ? true
            : null,
      value: state?.setup_kind ?? undefined,
    },
    {
      id: "filters",
      label: "Filters",
      Icon: Filter,
      ok: filters,
      value:
        filters === null
          ? undefined
          : filters
            ? "clear"
            : "blocked",
    },
    {
      id: "risk",
      label: "Risk",
      Icon: Scale,
      ok:
        state?.sleeve_fraction != null || state?.confidence != null
          ? true
          : null,
      value: state
        ? `sleeve ${fmt((state.sleeve_fraction ?? 0) * 100, 0)}% · conf ${fmt((state.confidence ?? 0) * 100, 0)}%`
        : undefined,
    },
    {
      id: "meta",
      label: "Meta",
      Icon: BrainCircuit,
      ok: hasMeta ? (state?.hit_probability != null ? true : null) : null,
      value: hasMeta
        ? state?.hit_probability != null
          ? `hit ${fmt((state.hit_probability ?? 0) * 100, 0)}%`
          : "v15+"
        : "n/a",
    },
    {
      id: "action",
      label: "Action",
      Icon: Target,
      ok: plan?.action
        ? !String(plan.action).toUpperCase().includes("AVOID")
        : null,
      value: plan?.action
        ? size
          ? `${plan.action} · ${size.shares} sh`
          : plan.action
        : undefined,
    },
  ];

  return defs.map((d, i) => ({
    id: d.id,
    label: d.label,
    Icon: d.Icon,
    value: d.value,
    status: statusFrom(phase, i, activeStage, d.ok),
  }));
}

export function nodeColors(status: StageStatus): {
  border: string;
  bg: string;
  fg: string;
} {
  switch (status) {
    case "running":
      return {
        border: "var(--td-brand)",
        bg: "var(--td-brand-soft)",
        fg: "var(--td-ink-100)",
      };
    case "pass":
      return {
        border: "var(--td-gate-pass)",
        bg: "color-mix(in oklch, var(--td-gate-pass) 12%, transparent)",
        fg: "var(--td-gate-pass)",
      };
    case "fail":
      return {
        border: "var(--td-gate-fail)",
        bg: "color-mix(in oklch, var(--td-gate-fail) 12%, transparent)",
        fg: "var(--td-gate-fail)",
      };
    case "neutral":
      return {
        border: "var(--td-gate-neutral)",
        bg: "var(--td-ink-800)",
        fg: "var(--td-ink-300)",
      };
    case "idle":
    default:
      return {
        border: "var(--td-ink-600)",
        bg: "var(--td-ink-900)",
        fg: "var(--td-ink-400)",
      };
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

export function PipelineFlow({
  state,
  plan,
  size,
  model,
  phase,
  activeStage,
}: PipelineFlowProps) {
  const stages = buildStages(state, plan, size, model, phase, activeStage);

  return (
    <section aria-label="Model processing pipeline" className="w-full">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h2
          className="text-[16px] font-medium"
          style={{ color: "var(--td-ink-100)" }}
        >
          Pipeline
        </h2>
        <span
          className="text-[11px]"
          style={{ color: "var(--td-ink-400)" }}
        >
          timing: sector → volume → 22 → 200
        </span>
      </div>

      <div className="flex items-stretch gap-0 overflow-x-auto pb-1">
        {stages.map((stage, i) => {
          const colors = nodeColors(stage.status);
          const Icon = stage.Icon;
          return (
            <div key={stage.id} className="flex min-w-0 flex-1 items-stretch">
              <div
                className="flex min-w-[88px] flex-1 flex-col gap-1.5 p-2 transition-[border-color,background-color] duration-[var(--td-dur-pipeline)] ease-[var(--td-ease)]"
                style={{
                  border: `1px solid ${colors.border}`,
                  background: colors.bg,
                  borderRadius: "var(--td-radius-sm)",
                  animation:
                    stage.status === "running"
                      ? "td-pipeline-pulse 1.2s var(--td-ease) infinite"
                      : undefined,
                  willChange: stage.status === "running" ? "box-shadow" : undefined,
                }}
              >
                <div className="flex items-center gap-1.5">
                  <Icon
                    size={14}
                    strokeWidth={1.75}
                    style={{ color: colors.fg, flexShrink: 0 }}
                    aria-hidden
                  />
                  <span
                    className="truncate text-[11px] font-medium"
                    style={{ color: colors.fg }}
                  >
                    {stage.label}
                  </span>
                </div>
                {stage.id === "action" && plan?.action && phase === "done" ? (
                  <ActionChip action={plan.action} size="sm" />
                ) : stage.value ? (
                  <span
                    className="tabular line-clamp-2 text-[10px] leading-snug"
                    style={{
                      fontFamily: "var(--td-font-mono)",
                      color: "var(--td-ink-300)",
                    }}
                    title={stage.value}
                  >
                    {stage.value}
                  </span>
                ) : (
                  <span
                    className="text-[10px]"
                    style={{ color: "var(--td-ink-500)" }}
                  >
                    {stage.status === "running" ? "…" : "—"}
                  </span>
                )}
              </div>
              {i < stages.length - 1 ? (
                <div
                  className="mx-0.5 flex w-3 shrink-0 items-center"
                  aria-hidden
                >
                  <div
                    className="h-px w-full"
                    style={{
                      background:
                        stage.status === "pass" || stage.status === "neutral"
                          ? "var(--td-ink-500)"
                          : "var(--td-ink-700)",
                    }}
                  />
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}
