"use client";

import type { CSSProperties, ReactNode } from "react";

export type ModelStatus =
  | "active"
  | "frozen"
  | "satellite"
  | "fail_oos"
  | string
  | null
  | undefined;

type ModelBadgesProps = {
  isWinner?: boolean;
  isDefault?: boolean;
  hasEngine?: boolean;
  status?: ModelStatus;
  className?: string;
};

function Badge({
  children,
  tone,
}: {
  children: ReactNode;
  tone: "winner" | "default" | "engine" | "status" | "fail" | "frozen";
}) {
  const styles: Record<typeof tone, CSSProperties> = {
    winner: {
      background: "var(--td-badge-winner-bg, var(--td-brand-soft, #2F6F7A26))",
      color: "var(--td-badge-winner-fg, var(--td-brand, #2F6F7A))",
      border: "1px solid transparent",
    },
    default: {
      background: "transparent",
      color: "var(--td-ink-200, #CBD5E1)",
      border: "1px solid var(--td-badge-default-border, var(--td-ink-500, #64748B))",
    },
    engine: {
      background: "var(--td-ink-800, #1A222C)",
      color: "var(--td-badge-engine-fg, var(--td-ink-200, #CBD5E1))",
      border: "1px solid var(--td-ink-600, #334155)",
    },
    status: {
      background: "var(--td-ink-800, #1A222C)",
      color: "var(--td-ink-300, #94A3B8)",
      border: "1px solid var(--td-ink-700, #243040)",
    },
    fail: {
      background: "color-mix(in oklch, var(--td-action-avoid) 14%, transparent)",
      color: "var(--td-badge-status-fail)",
      border: "1px solid transparent",
    },
    frozen: {
      background: "transparent",
      color: "var(--td-badge-status-frozen)",
      border: "1px solid var(--td-ink-600)",
    },
  };

  return (
    <span
      className="inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium tracking-wide uppercase rounded-sm whitespace-nowrap"
      style={styles[tone]}
    >
      {children}
    </span>
  );
}

function statusTone(status: string): "fail" | "frozen" | "status" {
  const s = status.toLowerCase();
  if (s.includes("fail")) return "fail";
  if (s.includes("frozen")) return "frozen";
  return "status";
}

function statusLabel(status: string): string {
  const s = status.toLowerCase().replace(/_/g, " ");
  if (s.includes("fail")) return "FAIL OOS";
  return s;
}

export function ModelBadges({
  isWinner,
  isDefault,
  hasEngine,
  status,
  className = "",
}: ModelBadgesProps) {
  return (
    <div className={`flex flex-wrap items-center gap-1 ${className}`}>
      {isWinner ? <Badge tone="winner">Winner</Badge> : null}
      {isDefault ? <Badge tone="default">Default</Badge> : null}
      {hasEngine ? <Badge tone="engine">Engine</Badge> : null}
      {status ? (
        <Badge tone={statusTone(String(status))}>{statusLabel(String(status))}</Badge>
      ) : null}
    </div>
  );
}
