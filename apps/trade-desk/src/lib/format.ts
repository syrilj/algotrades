/** Display helpers + action CSS-var mapping for Trade Desk UI. */

export function formatPct(
  value: number | null | undefined,
  digits = 1,
): string {
  if (value == null || Number.isNaN(value)) return "—";
  const pct = Math.abs(value) <= 1 && Math.abs(value) > 0 ? value * 100 : value;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(digits)}%`;
}

export function formatUsd(
  value: number | null | undefined,
  digits = 2,
): string {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

export function formatNum(
  value: number | null | undefined,
  digits = 2,
): string {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: digits,
    minimumFractionDigits: Number.isInteger(value) ? 0 : Math.min(digits, 2),
  }).format(value);
}

/** Maps plan.action → CSS custom property name (e.g. --td-action-buy-now). */
export function actionColorVar(action: string | null | undefined): string {
  const a = (action ?? "").toUpperCase();
  if (a.includes("BUY NOW")) return "--td-action-buy-now";
  if (a.includes("BUY BREAKOUT")) return "--td-action-buy-breakout";
  if (a.includes("BREAKOUT WATCH")) return "--td-action-breakout-watch";
  if (a.includes("PULLBACK")) return "--td-action-pullback";
  if (a.includes("AVOID")) return "--td-action-avoid";
  if (a.includes("WAIT")) return "--td-action-wait";
  return "--td-action-wait";
}

/** Class string using the action CSS variable for color. */
export function actionColorClass(action: string | null | undefined): string {
  const v = actionColorVar(action);
  const slug = v.replace(/^--td-action-/, "");
  return `td-action-${slug} text-[color:var(${v})]`;
}

export function sanitizeSymbol(raw: unknown): string | null {
  if (typeof raw !== "string") return null;
  const s = raw.trim().toUpperCase().replace(/[^A-Z0-9]/g, "");
  if (!s || s.length > 12) return null;
  return s;
}

export function isValidModelId(id: string): boolean {
  return id === "auto" || /^[a-zA-Z0-9_]+$/.test(id);
}
