"use client";

import type { LucideIcon } from "lucide-react";
import {
  Clock,
  CornerDownLeft,
  Eye,
  Rocket,
  ShieldAlert,
  Zap,
} from "lucide-react";
import type { ActionLabel } from "@/lib/types";
import { matchActionVarName } from "@/lib/actionColors";

type ActionStyle = {
  color: string;
  soft: string;
  dashed: boolean;
};

function actionIconFor(action: string | undefined | null): LucideIcon | null {
  const a = (action ?? "").toUpperCase();
  if (a.includes("BUY NOW") || a.includes("RISK_OK")) return Rocket;
  if (a.includes("BUY BREAKOUT")) return Zap;
  if (a.includes("BREAKOUT WATCH") || a.includes("SIZE_DOWN")) return Eye;
  if (a.includes("PULLBACK")) return CornerDownLeft;
  if (a.includes("AVOID") || a.includes("FLATTEN") || a.includes("STAND ASIDE") || a.includes("ABSTAIN"))
    return ShieldAlert;
  if (a.includes("WAIT") || a.includes("HALT_NEW") || a.includes("EQUITY_HEDGE") || a === "WATCH")
    return Clock;
  return null;
}

function softOf(token: string): string {
  return `color-mix(in oklch, ${token} 22%, transparent)`;
}

/**
 * Action-verdict → { color, soft, dashed }. The color-var lookup itself
 * (including the risk_assessment.py mode aliases: RISK_OK/SIZE_DOWN/
 * HALT_NEW/EQUITY_HEDGE/FLATTEN) is consolidated in `@/lib/actionColors`;
 * this only layers on the "dashed" (almost-ready) flag and the neutral
 * ink-400 fallback for a wholly unrecognized action string.
 */
export function actionStyle(action: string | undefined | null): ActionStyle {
  const a = (action ?? "").toUpperCase();
  const varName = matchActionVarName(a) ?? "--td-ink-400";
  const color = `var(${varName})`;
  const dashed = varName === "--td-action-wait" && a.includes("ALMOST");
  return { color, soft: softOf(color), dashed };
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
  const Icon = actionIconFor(action);
  const iconSize = size === "lg" ? 14 : size === "sm" ? 10 : 12;
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
        gap: "0.35rem",
      }}
    >
      {Icon ? <Icon size={iconSize} strokeWidth={1.75} aria-hidden /> : null}
      {action}
    </span>
  );
}
