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
import { nodeColors, StageStatus } from "@/components/pipeline/PipelineFlow";
import { ActionChip } from "@/components/ui/ActionChip";

type StaticStage = {
  id: string;
  label: string;
  Icon: LucideIcon;
  value: string;
  status: StageStatus;
  action?: string;
};

function buildStages(): StaticStage[] {
  return [
    {
      id: "ohlcv",
      label: "OHLCV",
      Icon: CandlestickChart,
      value: "price · volume · ATR",
      status: "pass",
    },
    {
      id: "va",
      label: "VA / POC",
      Icon: Layers,
      value: "POC · VAL · VAH",
      status: "pass",
    },
    {
      id: "htf",
      label: "HTF HA",
      Icon: Activity,
      value: "St.MACD-HA trend",
      status: "pass",
    },
    {
      id: "rule",
      label: "Rule",
      Icon: GitBranch,
      value: "setup candidate / side",
      status: "pass",
    },
    {
      id: "filters",
      label: "Filters",
      Icon: Filter,
      value: "VWAP · vol · red-flag · squeeze",
      status: "pass",
    },
    {
      id: "risk",
      label: "Risk",
      Icon: Scale,
      value: "Kelly / sleeve sizing",
      status: "pass",
    },
    {
      id: "meta",
      label: "Meta",
      Icon: BrainCircuit,
      value: "XGB hit probability",
      status: "neutral",
    },
    {
      id: "action",
      label: "Action",
      Icon: Target,
      value: "verdict + size",
      status: "pass",
      action: "BUY NOW",
    },
  ];
}

type ModelFlowProps = {
  model?: string;
  className?: string;
};

export function ModelFlow({ className = "" }: ModelFlowProps) {
  const stages = buildStages();

  return (
    <section aria-label="Model pipeline" className={`w-full ${className}`.trim()}>
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h2
          className="text-[16px] font-medium"
          style={{ color: "var(--td-ink-100)" }}
        >
          How this model works
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
                className="flex min-w-[88px] flex-1 flex-col gap-1.5 p-2 transition-[border-color,background,box-shadow] duration-[var(--td-dur-pipeline)] ease-[var(--td-ease)]"
                style={{
                  border: `1px solid ${colors.border}`,
                  background: colors.bg,
                  borderRadius: "var(--td-radius-sm)",
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
                {stage.action ? (
                  <ActionChip action={stage.action} size="sm" />
                ) : (
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
