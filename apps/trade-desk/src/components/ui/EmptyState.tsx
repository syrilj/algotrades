"use client";

import type { LucideIcon } from "lucide-react";

/**
 * Shared idle-desk empty state: icon + serif display heading + muted hint,
 * with an optional numbered how-to list for desks that need a next-action
 * checklist instead of (or alongside) a one-line hint.
 */
export function EmptyState({
  icon: Icon,
  title,
  hint,
  steps,
}: {
  icon: LucideIcon;
  title: string;
  hint?: string;
  steps?: string[];
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-4 py-16 text-center">
      <Icon
        className="size-8 text-[var(--td-ink-500,#7e7e7e)]"
        strokeWidth={1.75}
      />
      <p className="font-[family-name:var(--td-font-display,Georgia,serif)] text-xl text-[var(--td-ink-100,#ffffff)]">
        {title}
      </p>
      {hint ? (
        <p className="max-w-sm text-[13px] text-[var(--td-ink-400,#bbbbbb)]">
          {hint}
        </p>
      ) : null}
      {steps?.length ? (
        <ol
          className="mt-2 flex max-w-sm flex-col gap-1 text-left text-[13px]"
          style={{ color: "var(--td-ink-300)" }}
        >
          {steps.map((step, i) => (
            <li key={i}>
              {i + 1}. {step}
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}
