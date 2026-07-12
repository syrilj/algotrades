"use client";

type ScoreBarProps = {
  value: number;
  max?: number;
  winner?: boolean;
  className?: string;
};

export function ScoreBar({
  value,
  max = 1,
  winner = false,
  className = "",
}: ScoreBarProps) {
  const safeMax = max > 0 ? max : 1;
  const pct = Math.max(0, Math.min(100, (value / safeMax) * 100));

  return (
    <div className={`flex items-center gap-2 min-w-[7rem] ${className}`}>
      <div
        className="h-1.5 flex-1 rounded-sm overflow-hidden"
        style={{ background: "var(--td-score-track, var(--td-ink-700, #243040))" }}
        role="meter"
        aria-valuenow={Number(value.toFixed(3))}
        aria-valuemin={0}
        aria-valuemax={Number(safeMax.toFixed(3))}
        aria-label={`Score ${value.toFixed(3)}`}
      >
        <div
          className="h-full rounded-sm transition-[width] duration-300 ease-out"
          style={{
            width: `${pct}%`,
            background: winner
              ? "var(--td-score-bar-winner, var(--td-brand-muted, #1E4A52))"
              : "var(--td-score-bar, var(--td-brand, #2F6F7A))",
          }}
        />
      </div>
      <span
        className="tabular-nums text-[12px] w-10 text-right"
        style={{
          fontFamily: "var(--td-font-mono, ui-monospace, Menlo, monospace)",
          color: "var(--td-ink-200, #CBD5E1)",
        }}
      >
        {value.toFixed(2)}
      </span>
    </div>
  );
}
