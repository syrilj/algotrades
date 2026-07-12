"use client";

import type { ActionLabel } from "@/lib/types";

type ActionStyle = {
  color: string;
  soft: string;
  dashed: boolean;
};

export function actionStyle(action: string | undefined | null): ActionStyle {
  const a = (action ?? "").toUpperCase();

  if (a.includes("BUY NOW")) {
    return { color: "var(--td-action-buy-now)", soft: "#2F6B4F22", dashed: false };
  }
  if (a.includes("BUY BREAKOUT")) {
    return {
      color: "var(--td-action-buy-breakout)",
      soft: "#1F7A6B22",
      dashed: false,
    };
  }
  if (a.includes("BREAKOUT WATCH")) {
    return {
      color: "var(--td-action-breakout-watch)",
      soft: "#B0892E22",
      dashed: false,
    };
  }
  if (a.includes("PULLBACK")) {
    return {
      color: "var(--td-action-pullback)",
      soft: "#3D6E9C22",
      dashed: false,
    };
  }
  if (a.includes("AVOID")) {
    return { color: "var(--td-action-avoid)", soft: "#A3484822", dashed: false };
  }
  if (a.includes("WAIT")) {
    return {
      color: "var(--td-action-wait)",
      soft: "#6B778522",
      dashed: a.includes("ALMOST"),
    };
  }
  return { color: "var(--td-ink-400)", soft: "#64748B22", dashed: false };
}

/** Left-rail accent color for dense tables (Watch / Picks). */
export function actionRailColor(action: string | undefined | null): string {
  return actionStyle(action).color;
}

type ActionChipProps = {
  action: ActionLabel | string;
  size?: "sm" | "md" | "lg";
  className?: string;
};

export function ActionChip({ action, size = "md", className = "" }: ActionChipProps) {
  const style = actionStyle(action);
  const pad =
    size === "lg"
      ? "px-3 py-1.5 text-[13px]"
      : size === "sm"
        ? "px-1.5 py-0.5 text-[11px]"
        : "px-2 py-1 text-[12px]";

  return (
    <span
      className={`inline-flex items-center font-semibold tracking-wide ${pad} ${className}`}
      style={{
        color: style.color,
        background: style.soft,
        border: `1px ${style.dashed ? "dashed" : "solid"} ${style.color}`,
        borderRadius: "var(--td-radius-sm)",
      }}
    >
      {action}
    </span>
  );
}
