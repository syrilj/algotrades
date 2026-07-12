"use client";

import { Check, Minus, X } from "lucide-react";
import type { AnalyzeState } from "@/lib/types";

function fmt(n: number | null | undefined, digits = 2): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return n.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

type GateItem = { key: string; label: string; ok: boolean | null };

function buildCriticalGates(state: AnalyzeState): GateItem[] {
  const f = state.flags ?? {};
  return [
    { key: "hard", label: "Hard gates", ok: state.hard_gates_ok ?? null },
    {
      key: "setup",
      label: state.setup_kind ? `Setup ${state.setup_kind}` : "Setup",
      ok: state.setup_ok ?? null,
    },
    { key: "ha", label: "HTF HA", ok: f.htf_ha_green ?? null },
    {
      key: "vol",
      label: "Vol",
      ok:
        f.vol_confirm_or_pull ??
        (state.vol_surge === true ? true : state.vol_dry === true ? false : null),
    },
    { key: "red", label: "Not red-flag", ok: f.not_red_flag ?? null },
  ];
}

function buildAllGates(state: AnalyzeState): GateItem[] {
  const f = state.flags ?? {};
  return [
    ...buildCriticalGates(state),
    { key: "poc", label: "POC hold", ok: f.poc_hold ?? null },
    { key: "va", label: "In VA", ok: f.in_value_area ?? null },
    { key: "vwap", label: "VWAP trend", ok: f.vwap_uptrend ?? null },
    { key: "above_vwap", label: "Above VWAP", ok: f.above_vwap ?? null },
    { key: "sqz", label: "Squeeze off", ok: f.sqz_off_or_release ?? null },
    {
      key: "ema22",
      label: "EMA22",
      ok: state.above_ema22 ?? state.near_ema22 ?? null,
    },
    { key: "ema200", label: "EMA200", ok: state.above_ema200 ?? null },
  ];
}

type LadderMark = {
  id: string;
  label: string;
  value: number;
  color: string;
  kind: "zone" | "level" | "price";
};

function zoneCopy(state: AnalyzeState): string {
  const { price, val, vah } = state;
  if (price == null || val == null || vah == null || !(vah > val)) {
    return "Value zone incomplete — treat levels as advisory.";
  }
  if (price < val) return "Price below VAL — outside value, usually wait / avoid chase.";
  if (price > vah) return "Price above VAH — extension; breakout only if vol + structure hold.";
  return "Price inside value area — prefer pullback / POC logic over chase.";
}

type LevelsPanelProps = {
  state: AnalyzeState | null;
};

export function LevelsPanel({ state }: LevelsPanelProps) {
  if (!state) {
    return (
      <section className="td-panel p-4" aria-label="Levels">
        <p className="text-[12px]" style={{ color: "var(--td-ink-500)" }}>
          Value ladder and critical gates appear after analyze.
        </p>
      </section>
    );
  }

  const marks: LadderMark[] = [];
  const push = (
    id: string,
    label: string,
    value: number | null | undefined,
    color: string,
    kind: LadderMark["kind"],
  ) => {
    if (value != null && Number.isFinite(value)) {
      marks.push({ id, label, value, color, kind });
    }
  };

  push("vah", "VAH", state.vah, "var(--td-overlay-vah)", "zone");
  push("poc", "POC", state.poc, "var(--td-overlay-poc)", "zone");
  push("val", "VAL", state.val, "var(--td-overlay-val)", "zone");
  push("ema22", "EMA22", state.ema22, "var(--td-overlay-ema-22)", "level");
  push("ema200", "EMA200", state.ema200, "var(--td-overlay-ema-200)", "level");
  push("bo", "Breakout", state.breakout_level, "var(--td-accent)", "level");
  push("entry", "Entry", state.entry, "var(--td-action-buy-now)", "level");
  push("stop", "Stop", state.stop, "var(--td-action-avoid)", "level");
  push("px", "Price", state.price, "var(--td-ink-50)", "price");

  const values = marks.map((m) => m.value);
  const lo = values.length ? Math.min(...values) : 0;
  const hi = values.length ? Math.max(...values) : 1;
  const span = hi > lo ? hi - lo : 1;
  const pad = span * 0.08;
  const min = lo - pad;
  const max = hi + pad;
  const range = max - min || 1;

  const pct = (v: number) => ((v - min) / range) * 100;

  // Vertical ladder: high at top
  const sorted = [...marks].sort((a, b) => b.value - a.value);
  const critical = buildCriticalGates(state);
  const all = buildAllGates(state);

  return (
    <section className="td-panel flex flex-col gap-4 p-4" aria-label="Levels and checklist">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2
          className="text-[16px] font-medium"
          style={{ color: "var(--td-ink-100)" }}
        >
          Levels map
        </h2>
        <p className="text-[12px]" style={{ color: "var(--td-ink-400)" }}>
          {zoneCopy(state)}
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_220px]">
        {/* Horizontal bar with markers */}
        <div className="flex flex-col gap-3">
          <div
            className="relative h-10 w-full"
            style={{
              background: "var(--td-overlay-va-fill)",
              border: "1px solid var(--td-ink-600)",
              borderRadius: "var(--td-radius-sm)",
            }}
            role="img"
            aria-label={`Price ${fmt(state.price)} between ${fmt(min)} and ${fmt(max)}`}
          >
            {state.val != null && state.vah != null && state.vah > state.val ? (
              <div
                className="absolute inset-y-0"
                style={{
                  left: `${pct(state.val)}%`,
                  width: `${Math.max(2, pct(state.vah) - pct(state.val))}%`,
                  background: "color-mix(in oklch, var(--td-brand) 18%, transparent)",
                  borderLeft: "1px solid var(--td-overlay-val)",
                  borderRight: "1px solid var(--td-overlay-vah)",
                }}
                title="Value area"
              />
            ) : null}
            {marks.map((m) => (
              <div
                key={m.id}
                className="absolute top-0 bottom-0 flex flex-col items-center"
                style={{ left: `${pct(m.value)}%`, transform: "translateX(-50%)" }}
                title={`${m.label} ${fmt(m.value)}`}
              >
                <div
                  className={m.kind === "price" ? "w-0.5 flex-1" : "w-px flex-1"}
                  style={{
                    background: m.color,
                    opacity: m.kind === "price" ? 1 : 0.85,
                  }}
                />
                {m.kind === "price" ? (
                  <div
                    className="absolute top-1/2 h-3 w-3 -translate-y-1/2"
                    style={{
                      background: m.color,
                      border: "2px solid var(--td-ink-950)",
                      borderRadius: 1,
                    }}
                  />
                ) : null}
              </div>
            ))}
          </div>

          <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-[12px]">
            {sorted.map((m) => (
              <span key={m.id} className="inline-flex items-baseline gap-1.5">
                <span style={{ color: m.color }} className="text-[11px] font-semibold">
                  {m.label}
                </span>
                <span
                  className="tabular"
                  style={{
                    fontFamily: "var(--td-font-mono)",
                    color: m.kind === "price" ? "var(--td-ink-50)" : "var(--td-ink-100)",
                    fontWeight: m.kind === "price" ? 600 : 400,
                  }}
                >
                  {fmt(m.value)}
                </span>
              </span>
            ))}
          </div>
        </div>

        {/* Vertical ladder list */}
        <div
          className="flex flex-col gap-0 border-l pl-3"
          style={{ borderColor: "var(--td-ink-700)" }}
          aria-label="Price ladder"
        >
          {sorted.map((m) => (
            <div
              key={`v-${m.id}`}
              className="flex items-center justify-between gap-2 py-1 text-[12px]"
              style={{
                borderBottom:
                  m.kind === "price" ? "1px dashed var(--td-ink-600)" : undefined,
              }}
            >
              <span style={{ color: m.color, fontWeight: m.kind === "price" ? 700 : 500 }}>
                {m.label}
              </span>
              <span
                className="tabular"
                style={{
                  fontFamily: "var(--td-font-mono)",
                  color: "var(--td-ink-100)",
                }}
              >
                {fmt(m.value)}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h3
          className="mb-2 text-[12px] font-medium"
          style={{ color: "var(--td-ink-300)" }}
        >
          Critical gates
        </h3>
        <ul className="flex flex-wrap gap-2">
          {critical.map((g) => (
            <GateChip key={g.key} item={g} />
          ))}
        </ul>
        <details className="td-details mt-3">
          <summary className="td-details__summary">All gates</summary>
          <ul className="mt-2 flex flex-wrap gap-2">
            {all.map((g) => (
              <GateChip key={`all-${g.key}`} item={g} />
            ))}
          </ul>
        </details>
      </div>
    </section>
  );
}

function GateChip({ item }: { item: GateItem }) {
  const ok = item.ok;
  const color =
    ok === true
      ? "var(--td-gate-pass)"
      : ok === false
        ? "var(--td-gate-fail)"
        : "var(--td-gate-neutral)";
  const Icon = ok === true ? Check : ok === false ? X : Minus;

  return (
    <li
      className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[11px]"
      style={{
        color,
        border: `1px solid ${color}`,
        borderRadius: "var(--td-radius-sm)",
        background: "var(--td-ink-900)",
      }}
    >
      <Icon size={12} strokeWidth={1.75} aria-hidden />
      <span>{item.label}</span>
    </li>
  );
}
