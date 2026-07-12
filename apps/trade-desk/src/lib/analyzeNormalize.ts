/** Normalize trade_desk.py --json analyze payloads for Analyze + Watch. */

import type { AnalyzeResponse, PlainPlan } from "@/lib/types";

export function derivePlan(state: AnalyzeResponse["state"]): PlainPlan {
  const action = ((): PlainPlan["action"] => {
    if (state.breakout_buy) return "BUY NOW";
    if (state.breakout_ready) return "BUY BREAKOUT";
    if (state.setup_ok && state.entry != null) return "BUY NOW";
    if (state.setup_kind === "avoid" || state.hard_gates_ok === false) {
      // hard_gates false alone is often breakout_watch / incomplete — not always AVOID
      if (state.setup_kind === "breakout_watch" || state.breakout_ready) {
        return "BREAKOUT WATCH";
      }
      if (state.setup_kind === "avoid") return "AVOID";
      if (state.hard_gates_ok === false && !state.setup_ok) {
        // keep soft wait when still a constructive structure
        if (state.breakout_level != null && state.price != null) {
          return state.price < state.breakout_level
            ? "BREAKOUT WATCH"
            : "PULLBACK ZONE";
        }
        return "WAIT";
      }
      return "AVOID";
    }
    if (state.breakout_level != null && state.price != null) {
      return state.price < state.breakout_level
        ? "BREAKOUT WATCH"
        : "PULLBACK ZONE";
    }
    return "WAIT";
  })();

  const missing = Array.isArray(state.missing)
    ? (state.missing as string[])
    : [];

  const why =
    state.setup_kind && state.setup_kind !== "none"
      ? `setup: ${state.setup_kind} · conf ${((state.confidence ?? 0) * 100).toFixed(0)}%`
      : `confidence ${((state.confidence ?? 0) * 100).toFixed(0)}% · ${missing.length ? `${missing.length} gate(s) missing` : "all gates clear"}`;

  const doNext =
    action === "BUY NOW"
      ? `Enter ${state.entry ? `near ${state.entry.toFixed(2)}` : "at market"}, stop ${state.stop?.toFixed(2) ?? "—"}, trail ${state.trail_arm?.toFixed(2) ?? "—"}.`
      : action === "BUY BREAKOUT"
        ? `Buy a break above ${state.breakout_level?.toFixed(2) ?? "—"}, stop ${state.stop?.toFixed(2) ?? "—"}.`
        : action === "BREAKOUT WATCH"
          ? `Watch for a break above ${state.breakout_level?.toFixed(2) ?? "—"}.`
          : action === "PULLBACK ZONE"
            ? `Wait for a pullback toward entry ${state.entry?.toFixed(2) ?? "—"}.`
            : action === "AVOID"
              ? `Gates not met. Avoid or wait for a reset.`
              : `Conditions not fully aligned. Monitor for a clearer setup.`;

  return {
    action,
    why,
    do_next: doNext,
    confidence_note: missing.length
      ? `missing: ${missing.join(", ")}`
      : undefined,
  };
}

export function normalizeAnalyze(data: unknown): AnalyzeResponse {
  const d = (data && typeof data === "object"
    ? { ...(data as Record<string, unknown>) }
    : {}) as Record<string, unknown>;

  if (d.sizing != null && d.size == null) {
    d.size = d.sizing;
  }

  const stateRaw = (d.state ?? {}) as AnalyzeResponse["state"];
  // Ensure symbol bubbles up for watch rows
  if (!stateRaw.symbol && typeof d.symbol === "string") {
    stateRaw.symbol = d.symbol;
  }
  if (!stateRaw.model && typeof d.model === "string") {
    stateRaw.model = d.model as string;
  }
  d.state = stateRaw;

  if (d.plan == null) {
    d.plan = derivePlan(stateRaw);
  }

  return d as AnalyzeResponse;
}
