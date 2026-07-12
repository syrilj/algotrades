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

function buildGates(state: AnalyzeState): GateItem[] {
  const f = state.flags ?? {};
  return [
    { key: "poc", label: "POC hold", ok: f.poc_hold ?? null },
    { key: "va", label: "In VA", ok: f.in_value_area ?? null },
    { key: "ha", label: "HTF HA", ok: f.htf_ha_green ?? null },
    { key: "vwap", label: "VWAP trend", ok: f.vwap_uptrend ?? null },
    { key: "above_vwap", label: "Above VWAP", ok: f.above_vwap ?? null },
    {
      key: "vol",
      label: "Vol confirm",
      ok:
        f.vol_confirm_or_pull ??
        (state.vol_surge === true ? true : state.vol_dry === true ? false : null),
    },
    { key: "red", label: "Not red-flag", ok: f.not_red_flag ?? null },
    { key: "sqz", label: "Squeeze off", ok: f.sqz_off_or_release ?? null },
    {
      key: "ema22",
      label: "EMA22",
      ok: state.above_ema22 ?? state.near_ema22 ?? null,
    },
    { key: "ema200", label: "EMA200", ok: state.above_ema200 ?? null },
    { key: "hard", label: "Hard gates", ok: state.hard_gates_ok ?? null },
  ];
}

type LevelsPanelProps = {
  state: AnalyzeState | null;
};

export function LevelsPanel({ state }: LevelsPanelProps) {
  if (!state) {
    return (
      <section
        className="border-t py-4"
        style={{ borderColor: "var(--td-ink-700)" }}
        aria-label="Levels"
      >
        <p className="text-[12px]" style={{ color: "var(--td-ink-500)" }}>
          Value zone and checklist appear after analyze.
        </p>
      </section>
    );
  }

  const val = state.val;
  const vah = state.vah;
  const poc = state.poc;
  const price = state.price;
  let pocPct = 50;
  if (val != null && vah != null && vah > val && poc != null) {
    pocPct = Math.max(0, Math.min(100, ((poc - val) / (vah - val)) * 100));
  }
  let pricePct: number | null = null;
  if (val != null && vah != null && vah > val && price != null) {
    pricePct = Math.max(0, Math.min(100, ((price - val) / (vah - val)) * 100));
  }

  const gates = buildGates(state);

  return (
    <section
      className="flex flex-col gap-4 border-t py-4"
      style={{ borderColor: "var(--td-ink-700)" }}
      aria-label="Levels and checklist"
    >
      <div>
        <h2
          className="mb-2 text-[16px] font-medium"
          style={{ color: "var(--td-ink-100)" }}
        >
          Value zone
        </h2>
        <div className="flex flex-wrap items-center gap-4 text-[12px]">
          <LevelTag label="VAL" value={fmt(val)} color="var(--td-overlay-val)" />
          <LevelTag label="POC" value={fmt(poc)} color="var(--td-overlay-poc)" />
          <LevelTag label="VAH" value={fmt(vah)} color="var(--td-overlay-vah)" />
          <LevelTag
            label="EMA22"
            value={fmt(state.ema22)}
            color="var(--td-overlay-ema-22)"
          />
          <LevelTag
            label="EMA200"
            value={fmt(state.ema200)}
            color="var(--td-overlay-ema-200)"
          />
          {state.breakout_level != null ? (
            <LevelTag
              label="Breakout"
              value={fmt(state.breakout_level)}
              color="var(--td-accent)"
            />
          ) : null}
        </div>

        <div
          className="relative mt-3 h-3 w-full max-w-xl overflow-hidden"
          style={{
            background: "var(--td-overlay-va-fill)",
            border: "1px solid var(--td-ink-600)",
            borderRadius: "var(--td-radius-sm)",
          }}
          role="img"
          aria-label={`Value area from ${fmt(val)} to ${fmt(vah)}, POC ${fmt(poc)}`}
        >
          <div
            className="absolute inset-y-0 w-px"
            style={{
              left: `${pocPct}%`,
              background: "var(--td-overlay-poc)",
            }}
            title={`POC ${fmt(poc)}`}
          />
          {pricePct != null ? (
            <div
              className="absolute top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2"
              style={{
                left: `${pricePct}%`,
                background: "var(--td-ink-100)",
                borderRadius: 1,
              }}
              title={`Price ${fmt(price)}`}
            />
          ) : null}
        </div>
      </div>

      <div>
        <h3
          className="mb-2 text-[12px] font-medium"
          style={{ color: "var(--td-ink-300)" }}
        >
          Checklist gates
        </h3>
        <ul className="flex flex-wrap gap-2">
          {gates.map((g) => (
            <GateChip key={g.key} item={g} />
          ))}
        </ul>
      </div>
    </section>
  );
}

function LevelTag({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color: string;
}) {
  return (
    <span className="inline-flex items-baseline gap-1.5">
      <span style={{ color }} className="text-[11px] font-medium">
        {label}
      </span>
      <span
        className="tabular"
        style={{ fontFamily: "var(--td-font-mono)", color: "var(--td-ink-100)" }}
      >
        {value}
      </span>
    </span>
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
