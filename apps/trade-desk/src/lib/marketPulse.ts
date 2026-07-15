/**
 * Pure market-pulse shaping for the Trade Desk topbar.
 * Keeps fetch/network IO out of this module so unit tests call helpers directly.
 */

export type MarketPulseSeries = {
  key: string;
  label: string;
  /** Display value, already formatted for the operator (e.g. "16.2", "42 · Fear"). */
  display: string;
  /** Numeric value when known; null when unavailable. */
  value: number | null;
  /** Optional short change label (e.g. "+0.4", "risk-on"). */
  change?: string | null;
  /** Visual tone for the chip. */
  tone: "up" | "down" | "neutral" | "unavailable";
  source?: string | null;
};

export type MarketPulsePayload = {
  asof: string;
  series: MarketPulseSeries[];
  ok: boolean;
  error?: string | null;
};

export type RawQuote = {
  symbol: string;
  last: number | null;
  prevClose?: number | null;
  source?: string | null;
};

export type FearGreedRaw = {
  value: number | null;
  classification?: string | null;
  source?: string | null;
};

/** Map a raw last/prev into tone + optional signed change string. */
export function quoteTone(
  last: number | null | undefined,
  prevClose?: number | null,
): { tone: MarketPulseSeries["tone"]; change: string | null } {
  if (last == null || !Number.isFinite(last)) {
    return { tone: "unavailable", change: null };
  }
  if (prevClose == null || !Number.isFinite(prevClose) || prevClose === 0) {
    return { tone: "neutral", change: null };
  }
  const delta = last - prevClose;
  if (Math.abs(delta) < 1e-9) return { tone: "neutral", change: "0.0" };
  const sign = delta > 0 ? "+" : "";
  return {
    tone: delta > 0 ? "up" : "down",
    change: `${sign}${delta.toFixed(2)}`,
  };
}

/** VIX level → operator tone (higher VIX is risk-off / "down" for equities). */
export function vixTone(last: number | null | undefined): MarketPulseSeries["tone"] {
  if (last == null || !Number.isFinite(last)) return "unavailable";
  if (last >= 25) return "down";
  if (last <= 15) return "up";
  return "neutral";
}

/** Fear & Greed 0–100 → classification label. */
export function fearGreedLabel(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  if (value <= 24) return "Extreme Fear";
  if (value <= 44) return "Fear";
  if (value <= 55) return "Neutral";
  if (value <= 74) return "Greed";
  return "Extreme Greed";
}

export function fearGreedTone(
  value: number | null | undefined,
): MarketPulseSeries["tone"] {
  if (value == null || !Number.isFinite(value)) return "unavailable";
  if (value <= 44) return "down";
  if (value >= 56) return "up";
  return "neutral";
}

/**
 * Build the compact topbar series list from raw quotes + F&G.
 * Always returns three slots (VIX, F&G, Oil) so the UI layout is stable
 * even when one or more sources fail.
 */
export function buildMarketPulseSeries(input: {
  vix?: RawQuote | null;
  oil?: RawQuote | null;
  fearGreed?: FearGreedRaw | null;
  asof?: string;
}): MarketPulsePayload {
  const asof = input.asof ?? new Date().toISOString();
  const series: MarketPulseSeries[] = [];

  const vixLast = input.vix?.last ?? null;
  const vixQt = quoteTone(vixLast, input.vix?.prevClose);
  series.push({
    key: "vix",
    label: "VIX",
    display:
      vixLast != null && Number.isFinite(vixLast) ? vixLast.toFixed(1) : "—",
    value: vixLast != null && Number.isFinite(vixLast) ? vixLast : null,
    change: vixQt.change,
    tone: vixLast != null && Number.isFinite(vixLast) ? vixTone(vixLast) : "unavailable",
    source: input.vix?.source ?? null,
  });

  const fg = input.fearGreed?.value ?? null;
  const fgOk = fg != null && Number.isFinite(fg);
  const fgClass =
    input.fearGreed?.classification?.trim() ||
    (fgOk ? fearGreedLabel(fg) : null);
  series.push({
    key: "fear_greed",
    label: "F&G",
    display: fgOk
      ? `${Math.round(fg)}${fgClass ? ` · ${fgClass}` : ""}`
      : "—",
    value: fgOk ? fg : null,
    change: fgClass,
    tone: fearGreedTone(fg),
    source: input.fearGreed?.source ?? null,
  });

  const oilLast = input.oil?.last ?? null;
  const oilQt = quoteTone(oilLast, input.oil?.prevClose);
  series.push({
    key: "oil",
    label: "WTI",
    display:
      oilLast != null && Number.isFinite(oilLast)
        ? `$${oilLast.toFixed(2)}`
        : "—",
    value: oilLast != null && Number.isFinite(oilLast) ? oilLast : null,
    change: oilQt.change,
    tone:
      oilLast != null && Number.isFinite(oilLast) ? oilQt.tone : "unavailable",
    source: input.oil?.source ?? null,
  });

  const anyLive = series.some((s) => s.tone !== "unavailable" && s.value != null);
  return {
    asof,
    series,
    ok: anyLive,
    error: anyLive ? null : "Market pulse sources unavailable",
  };
}

/** Safe number parse for external payloads. */
export function finiteOrNull(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }
  return null;
}
