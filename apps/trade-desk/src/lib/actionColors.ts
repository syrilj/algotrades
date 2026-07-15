/**
 * Single source of truth for Trade Desk action/mode/gate/claim/regime color
 * lookups. Every chip/badge that maps a status string to a CSS custom
 * property should resolve its color through this file instead of
 * re-implementing its own if-chain.
 *
 * `colorVarFor` returns a *wrapped* CSS var reference, e.g.
 * `"var(--td-action-buy-now)"`, ready to hand to `<Chip colorVar={...} />`
 * or to interpolate directly into an inline style.
 *
 * NOTE: this file only fixes the broken `${c}22` tint mechanism and
 * consolidates duplicated lookup logic. It does not change any token/hex
 * color VALUES — those come in later tasks.
 */

export type ColorKind = "action" | "mode" | "gate" | "claim" | "regime" | "live_status";

/**
 * Ordered action-verdict matcher (bare CSS var name, no `var()` wrapper,
 * no default). Mirrors the historical `ActionChip.actionStyle` branch
 * order exactly (including the risk_assessment.py mode aliases), so every
 * previously-resolved color still resolves to the same var.
 */
export function matchActionVarName(value: string | null | undefined): string | null {
  // Normalize underscores so STAND_ASIDE / BUY_NOW match human labels.
  const a = (value ?? "").toUpperCase().replace(/_/g, " ");
  if (a.includes("BUY NOW") || a.includes("RISK OK")) return "--td-action-buy-now";
  if (a.includes("BUY BREAKOUT")) return "--td-action-buy-breakout";
  if (a.includes("BREAKOUT WATCH") || a.includes("SIZE DOWN")) return "--td-action-breakout-watch";
  if (a.includes("PULLBACK")) return "--td-action-pullback";
  if (
    a.includes("AVOID") ||
    a.includes("FLATTEN") ||
    a.includes("STAND ASIDE") ||
    a.includes("ABSTAIN")
  )
    return "--td-action-avoid";
  if (
    a.includes("WAIT") ||
    a.includes("HALT NEW") ||
    a.includes("EQUITY HEDGE") ||
    a.includes("WATCH")
  )
    return "--td-action-wait";
  return null;
}

/**
 * Bare CSS var name for an action verdict, defaulting to wait/neutral.
 * Kept for `format.ts`'s `actionColorVar` re-export (back-compat).
 */
export function actionColorVarName(value: string | null | undefined): string {
  return matchActionVarName(value) ?? "--td-action-wait";
}

/**
 * Options / risk-mode → color.
 *
 * Order matters: EQUITY_HEDGE contains "EQUITY" but must not resolve to the
 * long-equity accent. Prefer specific risk aliases (via matchActionVarName)
 * before the bare OPTIONS / EQUITY vehicle labels.
 */
function modeColorVarName(mode: string | null | undefined): string {
  const m = (mode ?? "").toUpperCase();
  // Risk-manager ticket modes (STAND_ASIDE, RISK_OK, SIZE_DOWN, EQUITY_HEDGE, …)
  const actionMatch = matchActionVarName(mode);
  if (actionMatch) return actionMatch;
  if (m.includes("OPTIONS")) return "--td-action-buy-now";
  // Bare equity vehicle only (not EQUITY_HEDGE — handled above as wait).
  if (m === "EQUITY" || m.startsWith("EQUITY_") || m.endsWith("_EQUITY")) {
    return "--td-action-buy-breakout";
  }
  if (m.includes("FLATTEN") || m.includes("HALT")) return "--td-action-avoid";
  return "--td-action-wait";
}

/** Pass/fail/neutral gate color (LevelsPanel/PipelineFlow/SupplyChainDesk confidence style). */
function gateColorVarName(value: string | null | undefined): string {
  const v = (value ?? "").toLowerCase();
  if (v === "pass") return "--td-gate-pass";
  if (v === "fail") return "--td-gate-fail";
  return "--td-gate-neutral";
}

/** EvolveDesk claim-level → color (foreground hue only; Chip derives the tint). */
function claimColorVarName(level: string | null | undefined): string {
  switch (level) {
    case "CLAIM":
      return "--td-action-buy-now";
    case "RESEARCH":
      return "--td-action-breakout-watch";
    case "THIN":
      return "--td-ink-400";
    case "ERROR":
    case "BLOCKED_DATA":
      return "--td-action-avoid";
    default:
      return "--td-ink-300";
  }
}

/** Gamma regime + squeeze label → color (grouped per the brief: "gamma's regime/squeeze mappings"). */
function regimeColorVarName(value: string | null | undefined): string {
  const v = (value ?? "").toLowerCase();
  if (v === "positive_gex_pin") return "--td-brand";
  if (v === "negative_gex_amplify") return "--td-action-avoid";
  if (v === "bullish_squeeze") return "--td-action-buy-now";
  if (v === "bearish_squeeze") return "--td-action-avoid";
  return "--td-action-wait"; // flat / neutral / unrecognized
}

/** Leaderboard live paper-trading status (Task 11) → color. */
function liveStatusColorVarName(value: string | null | undefined): string {
  const v = (value ?? "").toLowerCase();
  if (v === "confirming") return "--td-action-buy-now";
  if (v === "degrading") return "--td-action-avoid";
  if (v === "provisional") return "--td-action-wait";
  return "--td-action-wait"; // "none" / unrecognized
}

/**
 * Resolve a status string to a wrapped CSS var reference, e.g.
 * `"var(--td-action-buy-now)"`. This is the primary entry point for the
 * shared `<Chip>` primitive.
 */
export function colorVarFor(kind: ColorKind, value: string | null | undefined): string {
  switch (kind) {
    case "action":
      return `var(${actionColorVarName(value)})`;
    case "mode":
      return `var(${modeColorVarName(value)})`;
    case "gate":
      return `var(${gateColorVarName(value)})`;
    case "claim":
      return `var(${claimColorVarName(value)})`;
    case "regime":
      return `var(${regimeColorVarName(value)})`;
    case "live_status":
      return `var(${liveStatusColorVarName(value)})`;
    default: {
      const _exhaustive: never = kind;
      return _exhaustive;
    }
  }
}

/** LeaderboardTable medal color (rank 1/2/3/else), fallback hex preserved from the original `medalColor`. */
export function rankColorVar(rank: number): string {
  if (rank === 1) return "var(--td-rank-gold, #f4b400)";
  if (rank === 2) return "var(--td-rank-silver, #e6e6e6)";
  if (rank === 3) return "var(--td-rank-bronze, #b87336)";
  return "var(--td-rank-plain, var(--td-ink-400, #bbbbbb))";
}

/** SupplyChainDesk score → rank CSS class (thresholds preserved from the original `scoreClass`). */
export function scoreRankClass(score: number): string {
  if (score >= 0.75) return "td-rank-gold";
  if (score >= 0.55) return "td-rank-silver";
  if (score >= 0.35) return "td-rank-bronze";
  return "td-rank-plain";
}

/** SupplyChainDesk confidence ("high"/"low"/else) → gate color. */
export function confColorVar(conf: string | undefined): string {
  const c = (conf || "").toLowerCase();
  if (c === "high") return colorVarFor("gate", "pass");
  if (c === "low") return colorVarFor("gate", "fail");
  return colorVarFor("gate", "neutral");
}
