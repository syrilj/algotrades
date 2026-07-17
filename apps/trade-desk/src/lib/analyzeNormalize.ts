/** Normalize trade_desk.py --json analyze payloads for Analyze + Watch. */

import type { AnalyzeResponse, PlainPlan } from "@/lib/types";

/**
 * Fallback operator plan when Python did not attach `plan`.
 * Mirrors tools/trade_desk._plain_plan so Watch/Analyze stay actionable.
 */
export function derivePlan(state: AnalyzeResponse["state"]): PlainPlan {
  const missing = Array.isArray(state.missing)
    ? (state.missing as string[])
    : [];
  const conf = state.confidence ?? 0;
  const kind = state.setup_kind || (state.setup_ok ? "classic_buy" : "wait");
  const lvl = state.breakout_level;
  const e22 = state.ema22;
  const e200 = state.ema200;
  const rvol = state.rvol;
  const px = state.price;
  const stop = state.stop;
  const trail = state.trail_arm;
  const entry = state.entry;
  const val = state.val;
  const vah = state.vah;

  let action: PlainPlan["action"] = "WAIT";
  let why = "";
  let doNext = "";

  if (kind === "structural_break") {
    action = "AVOID (structure broken)";
    why =
      `Lost the 200 EMA` +
      (e200 != null ? ` ($${e200.toFixed(2)})` : "") +
      " — structural break. Don't buy dips until volume reclaims it.";
    doNext =
      `Stand aside. Watch for a volume surge reclaim of the 200` +
      (e200 != null ? ` ($${e200.toFixed(2)})` : "") +
      ". Until then, longs are fighting broken structure.";
  } else if (kind === "breakout_buy" || state.breakout_buy) {
    action = "BUY BREAKOUT";
    why =
      `Volume-led breakout` +
      (rvol != null ? ` (rvol ${rvol.toFixed(1)}x)` : "") +
      " — participation confirms the move. Smaller size.";
    const trigger = lvl != null ? `$${lvl.toFixed(2)}` : "breakout level";
    doNext =
      `Buy around $${(entry ?? px)?.toFixed(2) ?? "—"} (½–¾ normal size). ` +
      `Stop $${stop?.toFixed(2) ?? "—"}. ` +
      `Invalid if it fails back under ${trigger} or volume dies.`;
  } else if (kind === "classic_buy" || state.setup_ok) {
    action = "BUY NOW";
    if (state.near_ema22 && e22 != null) {
      why = `Pullback into the 22 EMA (~$${e22.toFixed(2)}) with structure intact — best R:R flavor.`;
    } else {
      why = "Pullback-in-value setup is live. Use the size/stop below.";
    }
    doNext =
      `Buy around $${(entry ?? px)?.toFixed(2) ?? "—"}. ` +
      `Hard stop $${stop?.toFixed(2) ?? "—"}. ` +
      `If it runs to $${trail?.toFixed(2) ?? "—"}, trail under the high.`;
  } else if (kind === "breakout_watch" || state.breakout_ready) {
    action = "BREAKOUT WATCH";
    why =
      "Near highs with volume waking — breakout precipitates when volume SURGES through the level.";
    const trigger = lvl != null ? `$${lvl.toFixed(2)}` : "the 20-bar high";
    if (lvl != null && px != null && px >= lvl * 0.998) {
      doNext =
        `Already pressing $${px.toFixed(2)}. Only buy on a VOLUME push through ${trigger} ` +
        `(rvol ≥ ~1.3x). Abort under $${stop?.toFixed(2) ?? "—"}.`;
    } else {
      doNext =
        `Alert above ${trigger}. Enter only when volume expands with the break; ` +
        `ignore a quiet drift through. Stop under $${stop?.toFixed(2) ?? "—"}.`;
    }
  } else if (kind === "pullback_watch") {
    action = "PULLBACK ZONE";
    if (state.near_ema22 && e22 != null) {
      why = `Trend OK — wait for / buy the dip into the 22 EMA (~$${e22.toFixed(2)}), not the extension.`;
      doNext =
        `Alert near 22 EMA $${e22.toFixed(2)}` +
        (val != null ? ` / VAL $${val.toFixed(2)}` : "") +
        ". Prefer quiet volume on the dip (healthy), then buy when volume returns up.";
    } else {
      why = "Trend is fine but price is chasing above value — wait for a dip.";
      if (vah != null && val != null) {
        doNext =
          `Alert near VAH $${vah.toFixed(2)} or VAL $${val.toFixed(2)}` +
          (e22 != null ? ` / 22 EMA $${e22.toFixed(2)}` : "") +
          (px != null ? `. Don't chase $${px.toFixed(2)}.` : ".");
      } else {
        doNext = "Wait for price to re-enter the value area before buying.";
      }
    }
  } else if (
    kind === "avoid" ||
    state.flags?.not_red_flag === false
  ) {
    // Hard AVOID only for explicit avoid kind or red-flag trap.
    // Dry volume alone is WAIT with levels (mirrors trade_desk._plain_plan).
    action = "AVOID";
    why = "Weak tape: price push on dying volume — classic trap. Volume is the veto.";
    doNext =
      "Stand aside until volume confirms (rvol > 1) or price resets into value / 22 EMA.";
  } else if (state.vol_dry) {
    action = "WAIT";
    const rvolS = rvol != null ? `${rvol.toFixed(1)}x` : "quiet";
    why = `Volume quiet (${rvolS}) · structure readiness ${(conf * 100).toFixed(0)}% — not a veto; wait for participation.`;
    const dryBits: string[] = [];
    if (e22 != null) dryBits.push(`dip zone 22 EMA $${e22.toFixed(2)}`);
    if (val != null) dryBits.push(`demand/VAL $${val.toFixed(2)}`);
    if (lvl != null) dryBits.push(`volume break $${lvl.toFixed(2)}`);
    doNext = dryBits.length
      ? `Watch: ${dryBits.slice(0, 3).join(" · ")}. Enter only when rvol expands.`
      : "Stand aside until rvol > 1 or price resets into value / 22 EMA.";
  } else if (state.breakout_level != null && state.price != null) {
    action =
      state.price < state.breakout_level ? "BREAKOUT WATCH" : "PULLBACK ZONE";
    if (action === "BREAKOUT WATCH") {
      why = `setup: breakout watch · conf ${(conf * 100).toFixed(0)}%`;
      doNext = `Watch for a volume break above $${state.breakout_level.toFixed(2)}. Not a buy yet.`;
    } else {
      why = `setup: extended · conf ${(conf * 100).toFixed(0)}%`;
      doNext = `Wait for a pullback toward entry ${entry != null ? `$${entry.toFixed(2)}` : "value"}.`;
    }
  } else if (missing.length <= 2 && conf >= 0.65) {
    action = "WAIT (almost ready)";
    why = `Only ${missing.length} check(s) left — close, but not a green light yet.`;
    doNext = missing.length
      ? `Still need: ${missing.join(", ")}`
      : "Conditions not fully aligned. Monitor for a clearer setup.";
  } else {
    action = "WAIT";
    const off = missing.slice(0, 3);
    why = `No long entry yet · structure readiness ${(conf * 100).toFixed(0)}%${
      off.length ? ` · still off: ${off.join(", ")}` : ""
    }.`;
    const bits: string[] = [];
    if (e22 != null) bits.push(`dip zone 22 EMA $${e22.toFixed(2)}`);
    if (val != null) bits.push(`demand/VAL $${val.toFixed(2)}`);
    if (lvl != null) bits.push(`volume break $${lvl.toFixed(2)}`);
    doNext = bits.length
      ? `Watch: ${bits.slice(0, 3).join(" · ")}. Stand aside until one path prints.`
      : off.length
        ? `Waiting on: ${off.join(", ")}`
        : "Conditions not fully aligned. Monitor for a clearer setup.";
  }

  return {
    action,
    why,
    do_next: doNext,
    confidence_note: missing.length
      ? `missing: ${missing.join(", ")}`
      : undefined,
    checklist: buildChecklistFromFlags(state.flags),
  };
}

const FLAG_LABELS: Record<string, string> = {
  poc_hold: "Holding above POC (support)",
  in_value_area: "Inside value area (not chasing)",
  htf_ha_green: "Bigger-timeframe trend is up",
  vwap_uptrend: "VWAP trend is up",
  above_vwap: "Price is above VWAP",
  vol_confirm_or_pull: "Volume confirms the move",
  not_red_flag: "Not a weak rally (vol drying up)",
  mom_pos: "Momentum is positive",
  sqz_off_or_release: "Squeeze released / not crushed",
  vol_surge: "Volume SURGE (breakout fuel)",
  vol_awake: "Volume waking vs average",
  not_vol_dry: "Volume not drying on the push",
  above_ema22: "Above 22 EMA (drawdown support)",
  above_ema200: "Above 200 EMA (structure intact)",
  near_ema22: "Near 22 EMA (pullback zone)",
};

export function buildChecklistFromFlags(flags?: Record<string, unknown>): { ok: boolean; label: string; key: string }[] {
  if (!flags || typeof flags !== "object") return [];
  return Object.keys(FLAG_LABELS).map((key) => {
    const ok = Boolean(flags[key]);
    return { ok, label: FLAG_LABELS[key], key };
  });
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

  // Prefer server plan; fill gaps if partial
  const existing = d.plan as PlainPlan | undefined | null;
  if (existing == null || typeof existing !== "object") {
    d.plan = derivePlan(stateRaw);
  } else {
    const p = { ...existing } as PlainPlan;
    if (!p.action) p.action = derivePlan(stateRaw).action;
    if (!p.do_next) p.do_next = derivePlan(stateRaw).do_next;
    if (!p.why) p.why = derivePlan(stateRaw).why;
    if (!p.checklist) p.checklist = buildChecklistFromFlags(stateRaw.flags);
    d.plan = p;
  }

  return d as AnalyzeResponse;
}
