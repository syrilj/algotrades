/**
 * Pure helpers for the top-bar market calendar and sector context.
 *
 * Dates are sourced from the official Federal Reserve, BLS, and BEA 2026
 * schedules. Keeping the small high-impact set here makes the shell reliable
 * when external calendar feeds are unavailable; source links remain attached.
 */

export type MarketEventImpact = "high" | "medium";

export type MarketEvent = {
  id: string;
  label: string;
  shortLabel: string;
  startsAt: string;
  impact: MarketEventImpact;
  note: string;
  source: "Federal Reserve" | "BLS" | "BEA" | "London Strategic Edge";
  sourceUrl: string;
};

export type SectorContext = {
  tone: "risk-on" | "defensive" | "mixed" | "unavailable";
  label: string;
  detail: string;
  leader: { etf: string; name: string; rs1d: number | null } | null;
  laggard: { etf: string; name: string; rs1d: number | null } | null;
  moneyIn: string[];
  moneyOut: string[];
  definitive: boolean;
  confidence: number | null;
  asofBar: string | null;
};

export type MarketContextPayload = {
  asof: string;
  events: MarketEvent[];
  eventSource?: "lse" | "verified_fallback";
  sectors: SectorContext;
};

const FED_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm";
const BLS_URL = "https://www.bls.gov/schedule/2026/home.htm";
const BEA_URL = "https://www.bea.gov/news/schedule/";

/** High-impact U.S. releases relevant to the desk, all times Eastern. */
export const IMPORTANT_MARKET_EVENTS: readonly MarketEvent[] = [
  {
    id: "fomc-2026-07",
    label: "FOMC rate decision",
    shortLabel: "FOMC",
    startsAt: "2026-07-29T14:00:00-04:00",
    impact: "high",
    note: "Decision 2:00 PM ET · press conference 2:30 PM ET",
    source: "Federal Reserve",
    sourceUrl: FED_URL,
  },
  {
    id: "gdp-pce-2026-07",
    label: "GDP advance estimate + PCE",
    shortLabel: "GDP + PCE",
    startsAt: "2026-07-30T08:30:00-04:00",
    impact: "high",
    note: "Q2 advance GDP and June income/outlays · 8:30 AM ET",
    source: "BEA",
    sourceUrl: BEA_URL,
  },
  {
    id: "nfp-2026-08",
    label: "Employment Situation",
    shortLabel: "Jobs",
    startsAt: "2026-08-07T08:30:00-04:00",
    impact: "high",
    note: "July payrolls and unemployment · 8:30 AM ET",
    source: "BLS",
    sourceUrl: BLS_URL,
  },
  {
    id: "cpi-2026-08",
    label: "Consumer Price Index",
    shortLabel: "CPI",
    startsAt: "2026-08-12T08:30:00-04:00",
    impact: "high",
    note: "July CPI and real earnings · 8:30 AM ET",
    source: "BLS",
    sourceUrl: BLS_URL,
  },
  {
    id: "gdp-pce-2026-08",
    label: "GDP second estimate + PCE",
    shortLabel: "GDP + PCE",
    startsAt: "2026-08-26T08:30:00-04:00",
    impact: "high",
    note: "Q2 second GDP estimate and July income/outlays · 8:30 AM ET",
    source: "BEA",
    sourceUrl: BEA_URL,
  },
  {
    id: "nfp-2026-09",
    label: "Employment Situation",
    shortLabel: "Jobs",
    startsAt: "2026-09-04T08:30:00-04:00",
    impact: "high",
    note: "August payrolls and unemployment · 8:30 AM ET",
    source: "BLS",
    sourceUrl: BLS_URL,
  },
  {
    id: "cpi-2026-09",
    label: "Consumer Price Index",
    shortLabel: "CPI",
    startsAt: "2026-09-11T08:30:00-04:00",
    impact: "high",
    note: "August CPI and real earnings · 8:30 AM ET",
    source: "BLS",
    sourceUrl: BLS_URL,
  },
  {
    id: "fomc-2026-09",
    label: "FOMC rate decision",
    shortLabel: "FOMC",
    startsAt: "2026-09-16T14:00:00-04:00",
    impact: "high",
    note: "Decision, projections, and press conference",
    source: "Federal Reserve",
    sourceUrl: FED_URL,
  },
  {
    id: "gdp-pce-2026-09",
    label: "GDP third estimate + PCE",
    shortLabel: "GDP + PCE",
    startsAt: "2026-09-30T08:30:00-04:00",
    impact: "high",
    note: "Q2 final GDP estimate and August income/outlays · 8:30 AM ET",
    source: "BEA",
    sourceUrl: BEA_URL,
  },
  {
    id: "nfp-2026-10",
    label: "Employment Situation",
    shortLabel: "Jobs",
    startsAt: "2026-10-02T08:30:00-04:00",
    impact: "high",
    note: "September payrolls and unemployment · 8:30 AM ET",
    source: "BLS",
    sourceUrl: BLS_URL,
  },
  {
    id: "cpi-2026-10",
    label: "Consumer Price Index",
    shortLabel: "CPI",
    startsAt: "2026-10-14T08:30:00-04:00",
    impact: "high",
    note: "September CPI and real earnings · 8:30 AM ET",
    source: "BLS",
    sourceUrl: BLS_URL,
  },
  {
    id: "fomc-2026-10",
    label: "FOMC rate decision",
    shortLabel: "FOMC",
    startsAt: "2026-10-28T14:00:00-04:00",
    impact: "high",
    note: "Decision 2:00 PM ET · press conference 2:30 PM ET",
    source: "Federal Reserve",
    sourceUrl: FED_URL,
  },
  {
    id: "gdp-pce-2026-10",
    label: "GDP advance estimate + PCE",
    shortLabel: "GDP + PCE",
    startsAt: "2026-10-29T08:30:00-04:00",
    impact: "high",
    note: "Q3 advance GDP and September income/outlays · 8:30 AM ET",
    source: "BEA",
    sourceUrl: BEA_URL,
  },
  {
    id: "nfp-2026-11",
    label: "Employment Situation",
    shortLabel: "Jobs",
    startsAt: "2026-11-06T08:30:00-05:00",
    impact: "high",
    note: "October payrolls and unemployment · 8:30 AM ET",
    source: "BLS",
    sourceUrl: BLS_URL,
  },
  {
    id: "cpi-2026-11",
    label: "Consumer Price Index",
    shortLabel: "CPI",
    startsAt: "2026-11-10T08:30:00-05:00",
    impact: "high",
    note: "October CPI and real earnings · 8:30 AM ET",
    source: "BLS",
    sourceUrl: BLS_URL,
  },
  {
    id: "gdp-pce-2026-11",
    label: "GDP second estimate + PCE",
    shortLabel: "GDP + PCE",
    startsAt: "2026-11-25T08:30:00-05:00",
    impact: "high",
    note: "Q3 second GDP estimate and October income/outlays · 8:30 AM ET",
    source: "BEA",
    sourceUrl: BEA_URL,
  },
  {
    id: "nfp-2026-12",
    label: "Employment Situation",
    shortLabel: "Jobs",
    startsAt: "2026-12-04T08:30:00-05:00",
    impact: "high",
    note: "November payrolls and unemployment · 8:30 AM ET",
    source: "BLS",
    sourceUrl: BLS_URL,
  },
  {
    id: "fomc-2026-12",
    label: "FOMC rate decision",
    shortLabel: "FOMC",
    startsAt: "2026-12-09T14:00:00-05:00",
    impact: "high",
    note: "Decision, projections, and press conference",
    source: "Federal Reserve",
    sourceUrl: FED_URL,
  },
  {
    id: "cpi-2026-12",
    label: "Consumer Price Index",
    shortLabel: "CPI",
    startsAt: "2026-12-10T08:30:00-05:00",
    impact: "high",
    note: "November CPI and real earnings · 8:30 AM ET",
    source: "BLS",
    sourceUrl: BLS_URL,
  },
  {
    id: "gdp-pce-2026-12",
    label: "GDP third estimate + PCE",
    shortLabel: "GDP + PCE",
    startsAt: "2026-12-23T08:30:00-05:00",
    impact: "high",
    note: "Q3 final GDP estimate and November income/outlays · 8:30 AM ET",
    source: "BEA",
    sourceUrl: BEA_URL,
  },
];

export function upcomingMarketEvents(
  now: Date = new Date(),
  limit = 5,
): MarketEvent[] {
  const t = now.getTime();
  return IMPORTANT_MARKET_EVENTS.filter(
    (event) => new Date(event.startsAt).getTime() >= t,
  )
    .sort((a, b) => +new Date(a.startsAt) - +new Date(b.startsAt))
    .slice(0, Math.max(0, limit));
}

type RawLseCalendarRow = {
  datetime?: unknown;
  event?: unknown;
  region?: unknown;
  country?: unknown;
  importance?: unknown;
  impact?: unknown;
  forecast?: unknown;
  previous?: unknown;
  actual?: unknown;
  source_url?: unknown;
};

const IMPORTANT_RELEASE =
  /\b(cpi|consumer price|fomc|fed|interest rate|nonfarm|payroll|employment|gdp|pce|inflation|unemployment|retail sales)\b/i;

function lseDate(value: unknown): string | null {
  if (typeof value !== "string" || !value.trim()) return null;
  let normalized = value.trim().replace(" ", "T");
  if (!/(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized)) normalized += "Z";
  const date = new Date(normalized);
  return Number.isFinite(date.getTime()) ? date.toISOString() : null;
}

function shortEventLabel(label: string): string {
  const lower = label.toLowerCase();
  if (lower.includes("fomc") || lower.includes("interest rate")) return "FOMC";
  if (lower.includes("consumer price") || /\bcpi\b/i.test(label)) return "CPI";
  if (lower.includes("payroll") || lower.includes("employment")) return "Jobs";
  if (/\bgdp\b/i.test(label)) return "GDP";
  if (/\bpce\b/i.test(label)) return "PCE";
  return label.length <= 12 ? label : label.slice(0, 12).trim();
}

/** Normalize provider rows into the stable shell calendar contract. */
export function marketEventsFromLse(
  raw: unknown,
  now: Date = new Date(),
  limit = 6,
): MarketEvent[] {
  if (!Array.isArray(raw)) return [];
  const nowMs = now.getTime();
  return (raw as RawLseCalendarRow[])
    .flatMap((row): MarketEvent[] => {
      const label = typeof row.event === "string" ? row.event.trim() : "";
      const startsAt = lseDate(row.datetime);
      if (!label || !startsAt || +new Date(startsAt) < nowMs) return [];
      const importance = String(row.importance ?? row.impact ?? "").toLowerCase();
      const high = importance === "high" || importance === "3";
      if (!high && !IMPORTANT_RELEASE.test(label)) return [];
      const region = String(row.region ?? row.country ?? "US").toUpperCase();
      const details = [
        row.forecast != null && row.forecast !== "" ? `forecast ${row.forecast}` : null,
        row.previous != null && row.previous !== "" ? `prior ${row.previous}` : null,
        row.actual != null && row.actual !== "" ? `actual ${row.actual}` : null,
      ].filter(Boolean);
      const slug = `${region}-${label}-${startsAt}`
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "")
        .slice(0, 96);
      return [
        {
          id: `lse-${slug}`,
          label,
          shortLabel: shortEventLabel(label),
          startsAt,
          impact: high ? "high" : "medium",
          note: `${region}${details.length ? ` · ${details.join(" · ")}` : " · scheduled release"}`,
          source: "London Strategic Edge",
          sourceUrl:
            typeof row.source_url === "string" && row.source_url.startsWith("https://")
              ? row.source_url
              : "https://londonstrategicedge.com",
        },
      ];
    })
    .sort((a, b) => +new Date(a.startsAt) - +new Date(b.startsAt))
    .slice(0, Math.max(0, limit));
}

export function eventCountdown(startsAt: string, now: Date = new Date()): string {
  const ms = new Date(startsAt).getTime() - now.getTime();
  if (!Number.isFinite(ms)) return "Scheduled";
  if (ms <= 0) return "Now";
  const hours = Math.ceil(ms / 3_600_000);
  if (hours < 24) return `in ${hours}h`;
  const days = Math.ceil(ms / 86_400_000);
  return `in ${days}d`;
}

export function eventDateLabel(startsAt: string): string {
  const date = new Date(startsAt);
  if (!Number.isFinite(date.getTime())) return "Date pending";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/New_York",
    timeZoneName: "short",
  }).format(date);
}

type RawSectorRow = {
  etf?: unknown;
  name?: unknown;
  rs_1d?: unknown;
  flow_direction?: unknown;
};

type RawSectorReport = {
  asof_bar?: unknown;
  sectors_ranked?: unknown;
  rotation?: {
    is_definitive?: unknown;
    confidence?: unknown;
    money_in_etfs?: unknown;
    money_out_etfs?: unknown;
  };
};

function finite(value: unknown): number | null {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

function strings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((v): v is string => typeof v === "string").slice(0, 5)
    : [];
}

/** Condense the existing sector-money-flow report into a top-bar desk read. */
export function summarizeSectorFlow(raw: unknown): SectorContext {
  const report = (raw && typeof raw === "object" ? raw : {}) as RawSectorReport;
  const rows = Array.isArray(report.sectors_ranked)
    ? (report.sectors_ranked as RawSectorRow[]).filter(
        (row) => typeof row?.etf === "string" && typeof row?.name === "string",
      )
    : [];
  const rotation = report.rotation ?? {};
  const moneyIn = strings(rotation.money_in_etfs);
  const moneyOut = strings(rotation.money_out_etfs);
  const leaderRow =
    rows.find((row) => row.flow_direction === "in") ?? rows[0] ?? null;
  const laggardRow =
    [...rows].reverse().find((row) => row.flow_direction === "out") ??
    rows.at(-1) ??
    null;
  const toSide = (row: RawSectorRow | null) =>
    row
      ? {
          etf: String(row.etf),
          name: String(row.name),
          rs1d: finite(row.rs_1d),
        }
      : null;
  const leader = toSide(leaderRow);
  const laggard = toSide(laggardRow);

  if (!leader && !laggard) {
    return {
      tone: "unavailable",
      label: "Sector pulse unavailable",
      detail: "Open Flow to run the full sector scan",
      leader: null,
      laggard: null,
      moneyIn,
      moneyOut,
      definitive: false,
      confidence: null,
      asofBar: typeof report.asof_bar === "string" ? report.asof_bar : null,
    };
  }

  const defensive = new Set(["XLP", "XLU", "XLV"]);
  const defensiveIn = moneyIn.filter((etf) => defensive.has(etf)).length;
  const growthIn = moneyIn.filter((etf) => !defensive.has(etf)).length;
  const tone: SectorContext["tone"] =
    defensiveIn >= 2 && defensiveIn > growthIn
      ? "defensive"
      : growthIn >= 2 && growthIn > defensiveIn
        ? "risk-on"
        : "mixed";

  return {
    tone,
    label: leader ? `${leader.etf} leads` : "Mixed sector tape",
    detail:
      leader && laggard
        ? `${leader.name} leading · ${laggard.name} weakest`
        : leader
          ? `${leader.name} leading the current scan`
          : `${laggard?.name ?? "Sector"} showing relative weakness`,
    leader,
    laggard,
    moneyIn,
    moneyOut,
    definitive: rotation.is_definitive === true,
    confidence: finite(rotation.confidence),
    asofBar: typeof report.asof_bar === "string" ? report.asof_bar : null,
  };
}

function icsEscape(value: string): string {
  return value
    .replace(/\\/g, "\\\\")
    .replace(/;/g, "\\;")
    .replace(/,/g, "\\,")
    .replace(/\n/g, "\\n");
}

function icsUtc(startsAt: string): string {
  return new Date(startsAt).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
}

/** Downloadable reminder calendar for the same high-impact events shown in the shell. */
export function buildMarketCalendarIcs(
  now: Date = new Date(),
  events: MarketEvent[] = upcomingMarketEvents(now, IMPORTANT_MARKET_EVENTS.length),
): string {
  const stamp = icsUtc(now.toISOString());
  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Trade Desk//Market Context//EN",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    "X-WR-CALNAME:Trade Desk — Market Events",
  ];
  for (const event of events.filter((event) => +new Date(event.startsAt) >= +now)) {
    const start = new Date(event.startsAt);
    const end = new Date(start.getTime() + 30 * 60_000);
    lines.push(
      "BEGIN:VEVENT",
      `UID:${event.id}@trade-desk.local`,
      `DTSTAMP:${stamp}`,
      `DTSTART:${icsUtc(event.startsAt)}`,
      `DTEND:${icsUtc(end.toISOString())}`,
      `SUMMARY:${icsEscape(`Market: ${event.label}`)}`,
      `DESCRIPTION:${icsEscape(`${event.note}\nSource: ${event.sourceUrl}`)}`,
      `URL:${event.sourceUrl}`,
      "BEGIN:VALARM",
      "TRIGGER:-PT60M",
      "ACTION:DISPLAY",
      `DESCRIPTION:${icsEscape(`${event.shortLabel} in 1 hour`)}`,
      "END:VALARM",
      "END:VEVENT",
    );
  }
  lines.push("END:VCALENDAR");
  return `${lines.join("\r\n")}\r\n`;
}
