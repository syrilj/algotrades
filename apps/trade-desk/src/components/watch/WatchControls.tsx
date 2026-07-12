"use client";

import { Loader2, Play, Square } from "lucide-react";

export type WatchControlsValue = {
  symbols: string;
  every: number;
  interval: string;
  model: string;
};

type WatchControlsProps = {
  value: WatchControlsValue;
  models: string[];
  running: boolean;
  loading?: boolean;
  onChange: (next: WatchControlsValue) => void;
  onStart: () => void;
  onStop: () => void;
};

const INTERVALS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"] as const;

export function WatchControls({
  value,
  models,
  running,
  loading = false,
  onChange,
  onStart,
  onStop,
}: WatchControlsProps) {
  const field =
    "h-8 rounded-[4px] border border-[var(--td-ink-600,#334155)] bg-[var(--td-ink-900,#12181F)] px-2 text-[13px] text-[var(--td-ink-100,#E2E8F0)] outline-none focus:ring-1 focus:ring-[var(--td-brand,#2F6F7A)]";

  return (
    <div className="flex flex-col gap-3 border-b border-[var(--td-ink-600,#334155)] bg-[var(--td-ink-800,#1A222C)] p-3">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex min-w-[220px] flex-1 flex-col gap-1">
          <span className="text-[12px] font-medium text-[var(--td-ink-300,#94A3B8)]">
            Watchlist
          </span>
          <input
            className={`${field} w-full font-[family-name:var(--td-font-mono,ui-monospace,Menlo,monospace)]`}
            value={value.symbols}
            onChange={(e) => onChange({ ...value, symbols: e.target.value })}
            placeholder="NVDA, MU, ANET"
            disabled={running}
            aria-label="Symbols (comma-separated)"
          />
        </label>

        <label className="flex w-[88px] flex-col gap-1">
          <span className="text-[12px] font-medium text-[var(--td-ink-300,#94A3B8)]">
            Every (s)
          </span>
          <input
            type="number"
            min={15}
            step={5}
            className={`${field} w-full tabular-nums`}
            value={value.every}
            onChange={(e) =>
              onChange({
                ...value,
                every: Math.max(15, Number(e.target.value) || 15),
              })
            }
            disabled={running}
            aria-label="Poll every N seconds (min 15)"
          />
        </label>

        <label className="flex w-[100px] flex-col gap-1">
          <span className="text-[12px] font-medium text-[var(--td-ink-300,#94A3B8)]">
            Interval
          </span>
          <select
            className={`${field} w-full`}
            value={value.interval}
            onChange={(e) => onChange({ ...value, interval: e.target.value })}
            disabled={running}
            aria-label="Bar interval"
          >
            {INTERVALS.map((iv) => (
              <option key={iv} value={iv}>
                {iv}
              </option>
            ))}
          </select>
        </label>

        <label className="flex min-w-[160px] flex-col gap-1">
          <span className="text-[12px] font-medium text-[var(--td-ink-300,#94A3B8)]">
            Model
          </span>
          <select
            className={`${field} w-full`}
            value={value.model}
            onChange={(e) => onChange({ ...value, model: e.target.value })}
            disabled={running}
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

        {running ? (
          <button
            type="button"
            onClick={onStop}
            className="inline-flex h-8 items-center gap-1.5 rounded-[4px] border border-[var(--td-ink-600,#334155)] bg-[var(--td-ink-700,#243040)] px-3 text-[13px] font-medium text-[var(--td-ink-100,#E2E8F0)] hover:bg-[var(--td-ink-600,#334155)]"
          >
            <Square className="size-3.5" strokeWidth={1.75} />
            Stop
          </button>
        ) : (
          <button
            type="button"
            onClick={onStart}
            disabled={loading || !value.symbols.trim()}
            className="inline-flex h-8 items-center gap-1.5 rounded-[4px] bg-[var(--td-brand,#2F6F7A)] px-3 text-[13px] font-medium text-[var(--td-ink-50,#F1F5F9)] hover:bg-[var(--td-brand-muted,#1E4A52)] disabled:opacity-40"
          >
            {loading ? (
              <Loader2 className="size-3.5 animate-spin" strokeWidth={1.75} />
            ) : (
              <Play className="size-3.5" strokeWidth={1.75} />
            )}
            Start
          </button>
        )}
      </div>
    </div>
  );
}
