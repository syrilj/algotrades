import type { UnusualOptionsFlag, UnusualOptionsFlow } from "./types";

type Row = Record<string, unknown>;

function pick(row: Row, ...keys: string[]): unknown {
  for (const key of keys) {
    const value = row[key];
    if (value != null && value !== "") return value;
  }
  return null;
}

function numberValue(value: unknown): number | null {
  if (value == null || value === "") return null;
  const number = typeof value === "number" ? value : Number(value);
  return Number.isFinite(number) ? number : null;
}

function textValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function osiParts(ticker: string | null): {
  expiry: string | null;
  right: "C" | "P" | null;
  strike: number | null;
} {
  const match = ticker?.toUpperCase().match(/^([A-Z.]+)(\d{6})([CP])(\d{8})$/);
  if (!match) return { expiry: null, right: null, strike: null };
  const date = match[2];
  return {
    expiry: `20${date.slice(0, 2)}-${date.slice(2, 4)}-${date.slice(4, 6)}`,
    right: match[3] as "C" | "P",
    strike: Number(match[4]) / 1000,
  };
}

function optionRight(value: unknown): "C" | "P" | null {
  const right = String(value ?? "").toLowerCase();
  if (right === "c" || right === "call") return "C";
  if (right === "p" || right === "put") return "P";
  return null;
}

function isoTime(value: unknown): string | null {
  const text = textValue(value);
  if (!text) return null;
  let normalized = text.replace(" ", "T");
  if (!/(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized)) normalized += "Z";
  const date = new Date(normalized);
  return Number.isFinite(date.getTime()) ? date.toISOString() : null;
}

function dteFor(expiry: string, now: Date): number {
  const expiryDate = new Date(`${expiry}T23:59:59Z`);
  return Math.max(0, Math.ceil((+expiryDate - +now) / 86_400_000));
}

export function normalizeLseOptionsFlow(
  raw: unknown,
  symbol: string,
  options: { now?: Date; topN?: number; minPremium?: number } = {},
): UnusualOptionsFlow {
  const rows = Array.isArray(raw) ? (raw as Row[]) : [];
  const now = options.now ?? new Date();
  const minPremium = options.minPremium ?? 25_000;
  const flags: Array<UnusualOptionsFlag & { trade_time?: string | null }> = [];
  let latestTime: string | null = null;
  let spot: number | undefined;

  for (const row of rows) {
    const ticker = textValue(pick(row, "ticker", "contract", "option_symbol"));
    const parsed = osiParts(ticker);
    const expiry =
      textValue(pick(row, "expiry", "expiration", "expiration_date")) ?? parsed.expiry;
    const right = optionRight(pick(row, "type", "right", "option_type")) ?? parsed.right;
    const strike = numberValue(pick(row, "strike", "strike_price")) ?? parsed.strike;
    if (!expiry || !right || strike == null || strike <= 0) continue;

    const price = numberValue(pick(row, "price", "trade_price", "last"));
    const contracts = numberValue(pick(row, "size", "quantity", "contracts", "volume"));
    const explicitPremium = numberValue(pick(row, "premium", "notional"));
    const premium =
      explicitPremium ??
      (price != null && contracts != null ? price * contracts * 100 : null);
    if (premium == null || premium < minPremium) continue;

    const rowSpot = numberValue(
      pick(row, "spot", "underlying_price", "underlyingPrice", "stock_price"),
    );
    if (spot == null && rowSpot != null) spot = rowSpot;
    const dte =
      numberValue(pick(row, "dte", "days_to_expiry")) ?? dteFor(expiry, now);
    const tradeTime = isoTime(pick(row, "ts", "datetime", "timestamp", "time"));
    if (tradeTime && (!latestTime || tradeTime > latestTime)) latestTime = tradeTime;

    const reasons = [`print:$${Math.round(premium).toLocaleString("en-US")}`];
    let score = 30 + Math.min(35, 12 * Math.log10(Math.max(1, premium / minPremium)));
    if ((contracts ?? 0) >= 100) {
      score += Math.min(15, Math.log10(contracts ?? 1) * 5);
      reasons.push(`size:${Math.round(contracts ?? 0)} contracts`);
    }
    if (dte <= 7) {
      score += 8;
      reasons.push(`short_dte:${Math.round(dte)}d`);
    }
    const moneyness = rowSpot && rowSpot > 0 ? ((strike - rowSpot) / rowSpot) * 100 : null;
    const isOtm =
      moneyness != null && ((right === "C" && moneyness > 2) || (right === "P" && moneyness < -2));
    if (isOtm) {
      score += 8;
      reasons.push(`otm_${right === "C" ? "call" : "put"}:${Math.abs(moneyness ?? 0).toFixed(1)}pct`);
    }
    score = Math.min(100, Math.round(score * 10) / 10);

    flags.push({
      symbol: symbol.toUpperCase().replace(".US", ""),
      expiry,
      dte: Math.round(dte),
      right,
      strike,
      spot: rowSpot ?? undefined,
      volume: contracts ?? 0,
      open_interest: numberValue(pick(row, "open_interest", "openInterest")) ?? undefined,
      mid: price,
      premium,
      iv: numberValue(pick(row, "iv", "implied_volatility")),
      moneyness_pct: moneyness,
      score,
      severity: premium >= 250_000 || score >= 65 ? "high" : score >= 45 ? "watch" : "info",
      reasons,
      reason: reasons.join("; "),
      unusual: true,
      methodology: "lse_options_time_and_sales",
      trade_time: tradeTime,
    });
  }

  flags.sort((a, b) => b.score - a.score || (b.premium ?? 0) - (a.premium ?? 0));
  const top = flags.slice(0, Math.max(1, options.topN ?? 20));
  const callPremium = flags
    .filter((row) => row.right === "C")
    .reduce((sum, row) => sum + (row.premium ?? 0), 0);
  const putPremium = flags
    .filter((row) => row.right === "P")
    .reduce((sum, row) => sum + (row.premium ?? 0), 0);

  return {
    ok: true,
    symbol: symbol.toUpperCase().replace(".US", ""),
    spot,
    n_scanned: rows.length,
    n_flagged: flags.length,
    flags: top,
    unusual: top,
    methodology: "lse_options_time_and_sales",
    methodology_note:
      "Individual LSE options prints with provider premium, IV, and Greeks when available; ranked by premium, size, DTE, and moneyness.",
    asof_utc: latestTime ?? now.toISOString(),
    session_label: "lse_options_time_and_sales",
    bias: callPremium === putPremium ? "balanced" : callPremium > putPremium ? "call" : "put",
  } as UnusualOptionsFlow;
}
