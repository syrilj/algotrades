"use client";

import type { LucideIcon } from "lucide-react";

/**
 * Shared idle-desk empty state: icon + display heading + muted hint,
 * with an optional numbered how-to list for desks that need a next-action
 * checklist instead of (or alongside) a one-line hint.
 */
export function EmptyState({
  icon: Icon,
  title,
  hint,
  code,
  steps,
}: {
  icon: LucideIcon;
  title: string;
  hint?: string;
  /** A literal command/snippet, rendered in a distinct monospace block. */
  code?: string;
  steps?: string[];
}) {
  return (
    <div className="td-empty" role="status">
      <div className="td-empty__icon" aria-hidden="true">
        <Icon size={22} strokeWidth={1.6} />
      </div>
      <p className="td-empty__title">{title}</p>
      {hint ? <p className="td-empty__hint">{hint}</p> : null}
      {code ? <pre className="td-empty__code">{code}</pre> : null}
      {steps?.length ? (
        <ol className="td-empty__steps">
          {steps.map((step, i) => (
            <li key={i}>
              <span className="td-empty__step-num">
                {String(i + 1).padStart(2, "0")}
              </span>
              <span>{step}</span>
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}
