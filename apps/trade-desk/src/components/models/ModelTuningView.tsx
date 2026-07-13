"use client";

import type { ModelMetaConfig } from "@/lib/types";

function fmt(n: number | undefined | null, digits = 2): string {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function TuningBar({
  label,
  value,
  max,
  color = "var(--td-brand)",
}: {
  label: string;
  value: number;
  max: number;
  color?: string;
}) {
  const pct = max > 0 ? Math.min(100, (Math.max(0, value) / max) * 100) : 0;
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between gap-2 text-[11px]">
        <span style={{ color: "var(--td-ink-300)" }}>{label}</span>
        <span
          className="tabular"
          style={{ fontFamily: "var(--td-font-mono)", color: "var(--td-ink-100)" }}
        >
          {fmt(value)}
        </span>
      </div>
      <div
        className="h-1.5 w-full overflow-hidden rounded-sm"
        style={{ background: "var(--td-ink-700)" }}
      >
        <div
          className="h-full rounded-sm"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
    </div>
  );
}

function TagChip({ children }: { children: string }) {
  return (
    <span
      className="inline-flex items-center px-1.5 py-0.5 text-[10px]"
      style={{
        color: "var(--td-ink-300)",
        border: "1px solid var(--td-ink-600)",
        background: "var(--td-ink-800)",
        borderRadius: "var(--td-radius-sm)",
      }}
    >
      {children}
    </span>
  );
}

type ModelTuningViewProps = {
  id: string;
  metaConfig?: ModelMetaConfig | null;
};

export function ModelTuningView({ id, metaConfig }: ModelTuningViewProps) {
  if (!metaConfig) {
    return (
      <section aria-label="Tuning">
        <div className="mb-3 flex items-baseline justify-between gap-3">
          <h2
            className="text-[16px] font-medium"
            style={{ color: "var(--td-ink-100)" }}
          >
            Tuning
          </h2>
          <span
            className="text-[11px]"
            style={{ color: "var(--td-ink-400)" }}
          >
            {id}
          </span>
        </div>
        <p className="text-[13px]" style={{ color: "var(--td-ink-400)" }}>
          No meta_config.json found for this engine.
        </p>
      </section>
    );
  }

  const genome = metaConfig.genome ?? {};
  const genomeEntries = Object.entries(genome).filter(
    ([, v]) => typeof v === "number",
  ) as [string, number][];
  const maxGenome = Math.max(1, ...genomeEntries.map(([, v]) => v));
  const featCols = metaConfig.feat_cols ?? [];
  const researchStack = metaConfig.research_stack ?? [];
  const params = metaConfig.params ?? {};
  const threshold = metaConfig.threshold;

  return (
    <section aria-label="Tuning">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h2
          className="text-[16px] font-medium"
          style={{ color: "var(--td-ink-100)" }}
        >
          Tuning
        </h2>
        <span
          className="text-[11px]"
          style={{ color: "var(--td-ink-400)" }}
        >
          {metaConfig.parent ? `${metaConfig.parent} → ${id}` : id}
        </span>
      </div>

      <div className="flex flex-col gap-4">
        {threshold != null ? (
          <TuningBar
            label="Threshold"
            value={threshold}
            max={1}
            color="var(--td-accent)"
          />
        ) : null}

        {genomeEntries.length > 0 ? (
          <div className="flex flex-col gap-2">
            <h3
              className="text-[12px] font-semibold uppercase tracking-wide"
              style={{ color: "var(--td-ink-400)" }}
            >
              Genome
            </h3>
            <div className="grid gap-2 sm:grid-cols-2">
              {genomeEntries.map(([k, v]) => (
                <TuningBar key={k} label={k} value={v} max={maxGenome} />
              ))}
            </div>
          </div>
        ) : null}

        {featCols.length > 0 ? (
          <div className="flex flex-col gap-2">
            <h3
              className="text-[12px] font-semibold uppercase tracking-wide"
              style={{ color: "var(--td-ink-400)" }}
            >
              Features
            </h3>
            <div className="flex flex-wrap gap-1.5">
              {featCols.map((c) => (
                <TagChip key={c}>{c}</TagChip>
              ))}
            </div>
          </div>
        ) : null}

        {researchStack.length > 0 ? (
          <div className="flex flex-col gap-2">
            <h3
              className="text-[12px] font-semibold uppercase tracking-wide"
              style={{ color: "var(--td-ink-400)" }}
            >
              Research stack
            </h3>
            <div className="flex flex-wrap gap-1.5">
              {researchStack.map((s) => (
                <TagChip key={s}>{s}</TagChip>
              ))}
            </div>
          </div>
        ) : null}

        {Object.keys(params).length > 0 ? (
          <div className="flex flex-col gap-2">
            <h3
              className="text-[12px] font-semibold uppercase tracking-wide"
              style={{ color: "var(--td-ink-400)" }}
            >
              Params
            </h3>
            <dl className="grid grid-cols-1 gap-1 text-[12px]">
              {Object.entries(params).map(([k, v]) => (
                <div
                  key={k}
                  className="flex items-baseline justify-between gap-2 py-0.5"
                  style={{ borderBottom: "1px solid var(--td-ink-700)" }}
                >
                  <dt style={{ color: "var(--td-ink-400)" }}>{k}</dt>
                  <dd
                    className="tabular"
                    style={{
                      fontFamily: "var(--td-font-mono)",
                      color: "var(--td-ink-200)",
                    }}
                  >
                    {String(v ?? "—")}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        ) : null}
      </div>
    </section>
  );
}
