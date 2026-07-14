"use client";

import type { ReactNode } from "react";

/**
 * Shared label/value stat cell. Uppercase muted label over a tabular value;
 * pass `emphasize` for the lead metrics in a summary grid.
 */
export function Stat({
  label,
  value,
  emphasize,
}: {
  label: string;
  value: ReactNode;
  emphasize?: boolean;
}) {
  return (
    <div className="flex flex-col">
      <span
        className="text-[10px] uppercase tracking-wider"
        style={{ color: "var(--td-ink-500)" }}
      >
        {label}
      </span>
      <span
        className={`tabular ${emphasize ? "text-[15px] font-medium" : "text-[13px]"}`}
        style={{ color: emphasize ? "var(--td-ink-100)" : "var(--td-ink-300)" }}
      >
        {value}
      </span>
    </div>
  );
}
