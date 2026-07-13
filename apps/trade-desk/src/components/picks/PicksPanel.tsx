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
    <div className="td-toolbar">
      <div className="td-toolbar__row">
        <div className="flex flex-col gap-1">
          <span className="td-label">Horizon</span>
          <div
            className="inline-flex rounded-md border border-[var(--td-hairline)] p-0.5"
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
                  className={`h-7 min-w-[64px] rounded-md px-3 text-[13px] font-medium capitalize ${
                    active
                      ? "bg-[var(--td-canvas)] text-[var(--td-ink)]"
                      : "text-[var(--td-body)] hover:bg-[var(--td-hairline)]"
                  }`}
                >
                  {h}
                </button>
              );
            })}
          </div>
        </div>

        <label className="td-field td-field--model">
          <span className="td-label">Model</span>
          <select
            className="td-input w-full"
            value={value.model}
            onChange={(e) => onChange({ ...value, model: e.target.value })}
            aria-label="Model"
            style={{ fontFamily: "var(--td-font-mono)" }}
          >
            <option value="auto">auto · pick best</option>
            {models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>

        <label className="td-field td-field--grow">
          <span className="td-label">Symbols override</span>
          <input
            className="td-input w-full"
            value={value.symbols}
            onChange={(e) => onChange({ ...value, symbols: e.target.value })}
            placeholder="optional: NVDA, MU"
            aria-label="Symbols override"
            style={{ fontFamily: "var(--td-font-mono)" }}
          />
        </label>

        <button
          type="button"
          onClick={onRun}
          disabled={loading}
          className="td-btn td-btn-primary"
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
        <span className="td-label">Sectors</span>
        <div className="flex flex-wrap gap-1.5">
          {SECTORS.map((sector) => {
            const active = value.sectors.includes(sector);
            return (
              <button
                key={sector}
                type="button"
                onClick={() => toggleSector(sector)}
                aria-pressed={active}
                className={`rounded-md border px-2 py-1 text-[12px] font-medium ${
                  active
                    ? "border-[var(--td-brand,#1c69d4)] bg-[var(--td-brand-soft,#1c69d426)] text-[var(--td-ink-100,#ffffff)]"
                    : "border-[var(--td-ink-600,#2b2b2b)] bg-[var(--td-ink-900,#0d0d0d)] text-[var(--td-ink-400,#bbbbbb)] hover:text-[var(--td-ink-200,#ffffff)]"
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
