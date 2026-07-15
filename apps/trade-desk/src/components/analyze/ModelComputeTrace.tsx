"use client";

import { useState } from "react";
import type { LucideIcon } from "lucide-react";
import {
  BrainCircuit,
  CandlestickChart,
  Check,
  ChevronRight,
  Filter,
  GitBranch,
  Minus,
  Scale,
  Target,
  X,
} from "lucide-react";
import type { AnalyzeState, ModelSelection, PlainPlan, PositionSize } from "@/lib/types";
import { formatPct } from "@/lib/format";

function fmt(n: number | null | undefined, digits = 2): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function fmtUsd(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

type ReplayStage = {
  id: string;
  label: string;
  Icon: LucideIcon;
  status: boolean | null;
  value: string;
  verdict: string;
  explanation: string;
  facts: Array<{ label: string; value: string }>;
};

function filterSummary(state: AnalyzeState) {
  const flags = state.flags ?? {};
  const entries = [
    ["VWAP trend", flags.vwap_uptrend],
    ["Above VWAP", flags.above_vwap],
    ["Volume", flags.vol_confirm_or_pull],
    ["No red flag", flags.not_red_flag],
    ["Squeeze release", flags.sqz_off_or_release],
  ] as const;
  const known = entries.filter(([, value]) => value !== undefined);
  const passed = known.filter(([, value]) => value === true).length;
  return { known, passed, clear: known.length ? passed === known.length : null };
}

function buildStages(state: AnalyzeState, plan: PlainPlan | null | undefined, size: PositionSize | null | undefined): ReplayStage[] {
  const flags = state.flags ?? {};
  const filters = filterSummary(state);
  const insideValue = flags.in_value_area;
  const breakout = state.breakout_level ?? state.entry;
  const action = plan?.action ?? "Decision pending";

  return [
    {
      id: "market",
      label: "Market context",
      Icon: CandlestickChart,
      status: state.price != null && state.poc != null ? true : null,
      value: `Price ${fmt(state.price)} · POC ${fmt(state.poc)}`,
      verdict: insideValue === true ? "Inside value" : "Market read",
      explanation: insideValue === true
        ? "Price is trading within the accepted value area. The engine avoids treating this as a chase and waits for confirmation at the breakout level."
        : "The engine first locates price against the session’s accepted value area before it evaluates the setup.",
      facts: [
        { label: "Price", value: fmt(state.price) },
        { label: "POC", value: fmt(state.poc) },
        { label: "Value area", value: `${fmt(state.val)} — ${fmt(state.vah)}` },
      ],
    },
    {
      id: "setup",
      label: "Setup signal",
      Icon: GitBranch,
      status: state.setup_ok ?? null,
      value: state.setup_kind ?? "No setup returned",
      verdict: state.setup_ok ? "Structure found" : "Structure incomplete",
      explanation: state.setup_ok
        ? `The engine found the ${state.setup_kind ?? "selected"} setup. This qualifies the idea for risk checks; it does not authorize an entry on its own.`
        : "The structure rule did not clear. The output remains conditional until the setup becomes valid.",
      facts: [
        { label: "Rule", value: state.setup_kind ?? "—" },
        { label: "Breakout", value: fmt(breakout) },
        { label: "HTF HA", value: flags.htf_ha_green === true ? "Aligned" : flags.htf_ha_green === false ? "Not aligned" : "—" },
      ],
    },
    {
      id: "gates",
      label: "Safety gates",
      Icon: Filter,
      status: filters.clear,
      value: filters.known.length ? `${filters.passed}/${filters.known.length} clear` : "No gate telemetry",
      verdict: filters.clear ? "Clear to continue" : "Condition remains",
      explanation: filters.clear
        ? "Trend, volume, and safety checks support the setup. The model can continue to risk sizing."
        : "One or more safety checks did not clear. The engine preserves the setup but reduces it to a monitored condition rather than a chased entry.",
      facts: filters.known.length
        ? filters.known.map(([label, value]) => ({ label, value: value ? "Pass" : "Hold" }))
        : [{ label: "Gate status", value: "—" }],
    },
    {
      id: "trigger",
      label: "Trigger level",
      Icon: Target,
      status: state.breakout_buy ?? (state.breakout_ready ? true : null),
      value: breakout != null ? `Break above ${fmt(breakout)}` : "No trigger level",
      verdict: state.breakout_buy ? "Trigger active" : "Watch, don’t chase",
      explanation: state.breakout_buy
        ? "Price has cleared the trigger condition. The ticket can move from monitoring to an executable entry, subject to the risk limit."
        : `The setup is not actionable until price breaks ${fmt(breakout)}. This is the condition that turns the idea into a trade.`,
      facts: [
        { label: "Trigger", value: fmt(breakout) },
        { label: "Spot", value: fmt(state.price) },
        { label: "Stop", value: fmt(state.stop) },
      ],
    },
    {
      id: "risk",
      label: "Risk sizing",
      Icon: Scale,
      status: size?.shares != null && size.shares > 0 ? true : null,
      value: size ? `${size.shares} sh · ${fmtUsd(size.dollar_risk)} risk` : "Sizing unavailable",
      verdict: size ? "Pre-sized" : "Size unavailable",
      explanation: size
        ? `Sizing converts the conditional setup into a bounded plan: ${size.shares} shares, capped at ${fmtUsd(size.dollar_risk)} if the stop is hit.`
        : "No account or risk budget was returned, so the engine cannot produce an executable share count.",
      facts: [
        { label: "Shares", value: size ? String(size.shares) : "—" },
        { label: "Risk", value: size ? fmtUsd(size.dollar_risk) : "—" },
        { label: "Confidence", value: formatPct(state.confidence, 0) },
      ],
    },
    {
      id: "decision",
      label: "Operator decision",
      Icon: BrainCircuit,
      status: plan?.action ? !plan.action.toUpperCase().includes("AVOID") : null,
      value: action,
      verdict: action,
      explanation: plan?.do_next ?? "The engine has not returned an operator instruction yet.",
      facts: [
        { label: "Action", value: action },
        { label: "Hit chance", value: formatPct(state.hit_probability, 0) },
        { label: "Model", value: state.model },
      ],
    },
  ];
}

function statusClass(status: boolean | null) {
  return status === true ? "pass" : status === false ? "hold" : "neutral";
}

function StatusMark({ status }: { status: boolean | null }) {
  if (status === true) return <Check size={14} aria-hidden />;
  if (status === false) return <X size={14} aria-hidden />;
  return <Minus size={14} aria-hidden />;
}

type ModelComputeTraceProps = {
  state: AnalyzeState | null;
  plan?: PlainPlan | null;
  size?: PositionSize | null;
  model?: string;
  selection?: ModelSelection | null;
};

export function ModelComputeTrace({ state, plan, size, model, selection }: ModelComputeTraceProps) {
  const [activeStage, setActiveStage] = useState(0);

  if (!state) {
    return (
      <section className="td-panel p-4" aria-label="Model decision replay">
        <p className="text-[13px]" style={{ color: "var(--td-ink-400)" }}>
          Run analysis to replay the model decision from market context to trade ticket.
        </p>
      </section>
    );
  }

  const stages = buildStages(state, plan, size);
  const current = stages[Math.min(activeStage, stages.length - 1)];
  const activeModel = model ?? state.model;

  return (
    <section className="td-decision-replay td-panel" aria-label="Model decision replay">
      <header className="td-decision-replay__header">
        <div>
          <p className="td-label">Analysis replay</p>
          <h2>How this decision was formed</h2>
        </div>
        <div className="td-decision-replay__engine">
          <span>Selected engine</span>
          <strong>{activeModel}</strong>
          {selection?.reason ? <small>{selection.reason}</small> : null}
        </div>
      </header>

      <div className="td-decision-replay__track" role="tablist" aria-label="Decision stages">
        {stages.map((stage, index) => {
          const status = statusClass(stage.status);
          const active = index === activeStage;
          return (
            <div className="td-decision-replay__segment" key={stage.id}>
              <button
                type="button"
                role="tab"
                aria-selected={active}
                className={`td-decision-replay__stage td-decision-replay__stage--${status}${active ? " is-active" : ""}`}
                onClick={() => setActiveStage(index)}
              >
                <span className="td-decision-replay__stage-number">{String(index + 1).padStart(2, "0")}</span>
                <span className="td-decision-replay__stage-mark"><StatusMark status={stage.status} /></span>
                <span className="td-decision-replay__stage-label inline-flex items-center gap-1">
                  <stage.Icon size={12} strokeWidth={1.75} aria-hidden />
                  {stage.label}
                </span>
                <span className="td-decision-replay__stage-value">{stage.value}</span>
              </button>
              {index < stages.length - 1 ? <ChevronRight className="td-decision-replay__arrow" size={16} aria-hidden /> : null}
            </div>
          );
        })}
      </div>

      <div className={`td-decision-replay__detail td-decision-replay__detail--${statusClass(current.status)}`} role="tabpanel">
        <div className="td-decision-replay__detail-copy">
          <span className="td-label">{current.label}</span>
          <h3>{current.verdict}</h3>
          <p>{current.explanation}</p>
        </div>
        <dl className="td-decision-replay__facts">
          {current.facts.map((fact) => (
            <div key={fact.label}>
              <dt>{fact.label}</dt>
              <dd>{fact.value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}
