"use client";

import { Loader2, Play, Radar, Square } from "lucide-react";

export type WatchControlsValue = {
  symbols: string;
  every: number;
  interval: string;
  model: string;
  /** open = core + hot sectors + movers; full = wider DEFAULT_WATCH universe */
  universe?: "open" | "full";
};

type WatchControlsProps = {
  value: WatchControlsValue;
  models: string[];
  running: boolean;
  loading?: boolean;
  scanning?: boolean;
  onChange: (next: WatchControlsValue) => void;
  onStart: () => void;
  onStop: () => void;
  /** Run full-market open scanner → fills watchlist with ranked plays */
  onMarketScan?: () => void;
};

const INTERVALS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"] as const;

export function WatchControls({
  value,
  models,
  running,
  loading = false,
  scanning = false,
  onChange,
  onStart,
  onStop,
  onMarketScan,
}: WatchControlsProps) {
  return (
    <div className="td-toolbar">
      <div className="td-toolbar__row">
        <label className="td-field td-field--grow">
          <span className="td-label">Watchlist</span>
          <input
            className="td-input w-full"
            value={value.symbols}
            onChange={(e) => onChange({ ...value, symbols: e.target.value })}
            placeholder="NVDA, MU, APLD — or Market scan"
            disabled={running || scanning}
            aria-label="Symbols (comma-separated)"
            style={{ fontFamily: "var(--td-font-mono)" }}
          />
        </label>

        <label className="td-field" style={{ width: "5.5rem" }}>
          <span className="td-label">Every (s)</span>
          <input
            type="number"
            min={15}
            step={5}
            className="td-input w-full tabular"
            value={value.every}
            onChange={(e) =>
              onChange({
                ...value,
                every: Math.max(15, Number(e.target.value) || 15),
              })
            }
            disabled={running}
            aria-label="Poll every N seconds (min 15)"
            style={{ fontFamily: "var(--td-font-mono)" }}
          />
        </label>

        <label className="td-field" style={{ width: "6.5rem" }}>
          <span className="td-label">Interval</span>
          <select
            className="td-input w-full"
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

        <label className="td-field td-field--model">
          <span className="td-label">Model</span>
          <select
            className="td-input w-full"
            value={value.model}
            onChange={(e) => onChange({ ...value, model: e.target.value })}
            disabled={running || scanning}
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

        <label className="td-field" style={{ width: "7.5rem" }}>
          <span className="td-label">Scan scope</span>
          <select
            className="td-input w-full"
            value={value.universe ?? "open"}
            onChange={(e) =>
              onChange({
                ...value,
                universe: e.target.value === "full" ? "full" : "open",
              })
            }
            disabled={running || scanning}
            aria-label="Market scan universe"
          >
            <option value="open">open · fast</option>
            <option value="full">wide · more names</option>
          </select>
        </label>

        <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
          {onMarketScan ? (
            <button
              type="button"
              onClick={onMarketScan}
              className="td-btn td-btn-ghost"
              disabled={running || scanning}
              title="Scan hot sectors + day movers + liquid names → rank with WINNER model (do next + math on board)"
            >
              {scanning ? (
                <Loader2 className="size-3.5 animate-spin" strokeWidth={1.75} />
              ) : (
                <Radar className="size-3.5" strokeWidth={1.75} />
              )}
              Market scan
            </button>
          ) : null}

          {running ? (
            <button type="button" onClick={onStop} className="td-btn td-btn-ghost">
              {loading ? (
                <Loader2 className="size-3.5 animate-spin" strokeWidth={1.75} />
              ) : (
                <Square className="size-3.5" strokeWidth={1.75} />
              )}
              Stop
            </button>
          ) : (
            <button
              type="button"
              onClick={onStart}
              className="td-btn td-btn-primary"
              disabled={scanning}
            >
              <Play className="size-3.5" strokeWidth={1.75} />
              Start
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
