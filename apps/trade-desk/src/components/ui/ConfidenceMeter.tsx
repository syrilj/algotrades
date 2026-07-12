"use client";

import { useEffect, useState } from "react";

type ConfidenceMeterProps = {
  value: number;
  label?: string;
};

/** value: 0–1; animates fill once on mount/update */
export function ConfidenceMeter({ value, label = "Confidence" }: ConfidenceMeterProps) {
  const clamped = Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0));
  const pct = Math.round(clamped * 100);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setReady(false);
    const id = requestAnimationFrame(() => setReady(true));
    return () => cancelAnimationFrame(id);
  }, [clamped]);

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-3">
        <span className="td-label mb-0" style={{ color: "var(--td-ink-300)" }}>
          {label}
        </span>
        <span
          className="tabular text-[13px] font-medium"
          style={{
            fontFamily: "var(--td-font-mono)",
            color: "var(--td-ink-100)",
          }}
        >
          {pct}%
        </span>
      </div>
      <div
        className="h-1.5 w-full overflow-hidden"
        style={{
          background: "var(--td-ink-700)",
          borderRadius: "var(--td-radius-sm)",
        }}
        role="meter"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        aria-label={label}
      >
        <div
          className="h-full origin-left"
          style={{
            width: `${pct}%`,
            background: "var(--td-brand)",
            borderRadius: "var(--td-radius-sm)",
            transform: ready ? "scaleX(1)" : "scaleX(0)",
            transition: ready
              ? `transform var(--td-dur-med) var(--td-ease)`
              : "none",
          }}
        />
      </div>
    </div>
  );
}
