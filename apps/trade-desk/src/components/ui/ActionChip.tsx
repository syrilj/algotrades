"use client";

import type { ActionLabel } from "@/lib/types";

type ActionStyle = {
  color: string;
  soft: string;
  dashed: boolean;
};

function softOf(token: string): string {
  return `color-mix(in oklch, ${token} 22%, transparent)`;
}

export function actionStyle(action: string | undefined | null): ActionStyle {
  const a = (action ?? "").toUpperCase();

  if (a.includes("BUY NOW")) {
    return {
      color: "var(--td-action-buy-now)",
      soft: softOf("var(--td-action-buy-now)"),
      dashed: false,
    };
  }
  if (a.includes("BUY BREAKOUT")) {
    return {
      color: "var(--td-action-buy-breakout)",
      soft: softOf("var(--td-action-buy-breakout)"),
      dashed: false,
    };
  }
  if (a.includes("BREAKOUT WATCH")) {
    return {
      color: "var(--td-action-breakout-watch)",
      soft: softOf("var(--td-action-breakout-watch)"),
      dashed: false,
    };
  }
  if (a.includes("PULLBACK")) {
    return {
      color: "var(--td-action-pullback)",
      soft: softOf("var(--td-action-pullback)"),
      dashed: false,
    };
  }
  if (a.includes("AVOID")) {
    return {
      color: "var(--td-action-avoid)",
      soft: softOf("var(--td-action-avoid)"),
      dashed: false,
    };
  }
  if (a.includes("WAIT")) {
    return {
      color: "var(--td-action-wait)",
      soft: softOf("var(--td-action-wait)"),
      dashed: a.includes("ALMOST"),
    };
  }
  // Risk assessment modes from tools/risk_assessment.py
  if (a.includes("RISK_OK")) {
    return {
      color: "var(--td-action-buy-now)",
      soft: softOf("var(--td-action-buy-now)"),
      dashed: false,
    };
  }
  if (a.includes("SIZE_DOWN")) {
    return {
      color: "var(--td-action-breakout-watch)",
      soft: softOf("var(--td-action-breakout-watch)"),
      dashed: false,
    };
  }
  if (a.includes("HALT_NEW") || a.includes("EQUITY_HEDGE")) {
    return {
      color: "var(--td-action-wait)",
      soft: softOf("var(--td-action-wait)"),
      dashed: false,
    };
  }
  if (a.includes("FLATTEN") || a.includes("AVOID")) {
    return {
      color: "var(--td-action-avoid)",
      soft: softOf("var(--td-action-avoid)"),
      dashed: false,
    };
  }
  return {
    color: "var(--td-ink-400)",
    soft: softOf("var(--td-ink-400)"),
    dashed: false,
  };
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
  const sizeClass =
    size === "lg"
      ? "td-action-chip--lg"
      : size === "sm"
        ? "td-action-chip--sm"
        : "td-action-chip--md";

  return (
    <span
      className={`td-action-chip ${sizeClass} ${className}`.trim()}
      style={{
        color: style.color,
        background: style.soft,
        border: `1px ${style.dashed ? "dashed" : "solid"} ${style.color}`,
      }}
    >
      {action}
    </span>
  );
}
