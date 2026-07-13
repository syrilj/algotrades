"use client";

export type LeaderboardMode = "portfolio" | "symbol";

type LeaderboardControlsProps = {
  mode: LeaderboardMode;
  symbol: string;
  enginesOnly: boolean;
  onModeChange: (mode: LeaderboardMode) => void;
  onSymbolChange: (symbol: string) => void;
  onEnginesOnlyChange: (value: boolean) => void;
  onRefresh?: () => void;
  loading?: boolean;
};

export function LeaderboardControls({
  mode,
  symbol,
  enginesOnly,
  onModeChange,
  onSymbolChange,
  onEnginesOnlyChange,
  onRefresh,
  loading,
}: LeaderboardControlsProps) {
  return (
    <div
      className="flex flex-wrap items-end gap-3 gap-y-2"
      style={{ color: "var(--td-ink-200, #ffffff)" }}
    >
      <div className="flex flex-col gap-1">
        <span
          className="text-[12px] font-medium"
          style={{ color: "var(--td-ink-400, #bbbbbb)" }}
        >
          Mode
        </span>
        <div
          className="inline-flex rounded-sm overflow-hidden"
          style={{ border: "1px solid var(--td-ink-600, #2b2b2b)" }}
          role="group"
          aria-label="Ranking mode"
        >
          {(["portfolio", "symbol"] as const).map((m) => {
            const active = mode === m;
            return (
              <button
                key={m}
                type="button"
                onClick={() => onModeChange(m)}
                className="px-3 py-1.5 text-[13px] transition-colors"
                style={{
                  background: active
                    ? "var(--td-canvas)"
                    : "var(--td-surface-card)",
                  color: active
                    ? "var(--td-ink)"
                    : "var(--td-body)",
                }}
                aria-pressed={active}
              >
                {m === "portfolio" ? "Portfolio" : "Per-symbol"}
              </button>
            );
          })}
        </div>
      </div>

      {mode === "symbol" ? (
        <label className="flex flex-col gap-1">
          <span
            className="text-[12px] font-medium"
            style={{ color: "var(--td-ink-400, #bbbbbb)" }}
          >
            Symbol
          </span>
          <input
            value={symbol}
            onChange={(e) => onSymbolChange(e.target.value.toUpperCase())}
            placeholder="IONQ"
            className="h-8 w-28 px-2 text-[13px] rounded-sm outline-none uppercase"
            style={{
              background: "var(--td-surface-card)",
              border: "1px solid var(--td-hairline)",
              color: "var(--td-ink)",
              fontFamily: "var(--td-font-mono, ui-monospace, Menlo, monospace)",
            }}
            aria-label="Symbol"
          />
        </label>
      ) : null}

      <label className="flex items-center gap-2 h-8 cursor-pointer select-none">
        <input
          type="checkbox"
          checked={enginesOnly}
          onChange={(e) => onEnginesOnlyChange(e.target.checked)}
          className="h-3.5 w-3.5 accent-[var(--td-brand,#1c69d4)]"
        />
        <span className="text-[13px]">Engines only</span>
      </label>

      {onRefresh ? (
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="h-8 px-3 text-[13px] rounded-sm transition-opacity disabled:opacity-50"
          style={{
            background: "transparent",
            border: "1px solid var(--td-ink)",
            color: "var(--td-ink)",
          }}
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      ) : null}
    </div>
  );
}
