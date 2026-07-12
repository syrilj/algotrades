"use client";

import { Loader2, ScanSearch } from "lucide-react";
import { SECTORS, type Sector } from "@/lib/types";

export type PicksHorizon = "day" | "week";

export type PicksPanelValue = {
  horizon: PicksHorizon;
  model: string;
  sectors: Sector[];
  symbols: string;
};

type PicksPanelProps = {
  value: PicksPanelValue;
  models: string[];
  loading?: boolean;
  onChange: (next: PicksPanelValue) => void;
  onRun: () => void;
};

const field =
  "h-8 rounded-[4px] border border-[var(--td-ink-600,#334155)] bg-[var(--td-ink-900,#12181F)] px-2 text-[13px] text-[var(--td-ink-100,#E2E8F0)] outline-none focus:ring-1 focus:ring-[var(--td-brand,#2F6F7A)]";

export function PicksPanel({
  value,
  models,
  loading = false,
  onChange,
  onRun,
}: PicksPanelProps) {
  const toggleSector = (sector: Sector) => {
    const has = value.sectors.includes(sector);
    onChange({
      ...value,
      sectors: has
        ? value.sectors.filter((s) => s !== sector)
        : [...value.sectors, sector],
    });
  };

  return (
    <div className="flex flex-col gap-3 border-b border-[var(--td-ink-600,#334155)] bg-[var(--td-ink-800,#1A222C)] p-3">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <span className="text-[12px] font-medium text-[var(--td-ink-300,#94A3B8)]">
            Horizon
          </span>
          <div
            className="inline-flex rounded-[4px] border border-[var(--td-ink-600,#334155)] p-0.5"
            role="group"
            aria-label="Horizon"
          >
            {(["day", "week"] as const).map((h) => {
              const active = value.horizon === h;
              return (
                <button
                  key={h}
                  type="button"
                  onClick={() => onChange({ ...value, horizon: h })}
                  className={`h-7 min-w-[64px] rounded-[3px] px-3 text-[13px] font-medium capitalize ${
                    active
                      ? "bg-[var(--td-brand,#2F6F7A)] text-[var(--td-ink-50,#F1F5F9)]"
                      : "text-[var(--td-ink-300,#94A3B8)] hover:bg-[var(--td-ink-700,#243040)]"
                  }`}
                >
                  {h}
                </button>
              );
            })}
          </div>
        </div>

        <label className="flex min-w-[160px] flex-col gap-1">
          <span className="text-[12px] font-medium text-[var(--td-ink-300,#94A3B8)]">
            Model
          </span>
          <select
            className={`${field} w-full`}
            value={value.model}
            onChange={(e) => onChange({ ...value, model: e.target.value })}
            aria-label="Model"
          >
            <option value="auto">auto</option>
            {models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>

        <label className="flex min-w-[180px] flex-1 flex-col gap-1">
          <span className="text-[12px] font-medium text-[var(--td-ink-300,#94A3B8)]">
            Symbols override
          </span>
          <input
            className={`${field} w-full font-[family-name:var(--td-font-mono,ui-monospace,Menlo,monospace)]`}
            value={value.symbols}
            onChange={(e) => onChange({ ...value, symbols: e.target.value })}
            placeholder="optional: NVDA, MU"
            aria-label="Symbols override"
          />
        </label>

        <button
          type="button"
          onClick={onRun}
          disabled={loading}
          className="inline-flex h-8 items-center gap-1.5 rounded-[4px] bg-[var(--td-brand,#2F6F7A)] px-3 text-[13px] font-medium text-[var(--td-ink-50,#F1F5F9)] hover:bg-[var(--td-brand-muted,#1E4A52)] disabled:opacity-40"
        >
          {loading ? (
            <Loader2 className="size-3.5 animate-spin" strokeWidth={1.75} />
          ) : (
            <ScanSearch className="size-3.5" strokeWidth={1.75} />
          )}
          Scan
        </button>
      </div>

      <div className="flex flex-col gap-1.5">
        <span className="text-[12px] font-medium text-[var(--td-ink-300,#94A3B8)]">
          Sectors
        </span>
        <div className="flex flex-wrap gap-1.5">
          {SECTORS.map((sector) => {
            const active = value.sectors.includes(sector);
            return (
              <button
                key={sector}
                type="button"
                onClick={() => toggleSector(sector)}
                aria-pressed={active}
                className={`rounded-[4px] border px-2 py-1 text-[12px] font-medium ${
                  active
                    ? "border-[var(--td-brand,#2F6F7A)] bg-[var(--td-brand-soft,#2F6F7A26)] text-[var(--td-ink-100,#E2E8F0)]"
                    : "border-[var(--td-ink-600,#334155)] bg-[var(--td-ink-900,#12181F)] text-[var(--td-ink-400,#64748B)] hover:text-[var(--td-ink-200,#CBD5E1)]"
                }`}
              >
                {sector}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
