import { NextResponse } from "next/server";

import {
  buildMarketCalendarIcs,
  marketEventsFromLse,
  summarizeSectorFlow,
  upcomingMarketEvents,
  type MarketContextPayload,
  type SectorContext,
} from "@/lib/marketContext";
import { runSectorMoneyFlow } from "@/lib/tradeDesk";
import { runLseEconomicCalendar } from "@/lib/tradeDesk";
import type { ApiEnvelope } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 30;

const CACHE_MS = 5 * 60_000;
let sectorCache: { at: number; data: SectorContext } | null = null;
let eventCache: { at: number; data: MarketContextPayload["events"] } | null = null;

function envelope(
  partial: Omit<ApiEnvelope<MarketContextPayload>, "asof"> & { asof?: string },
  status = 200,
): NextResponse {
  return NextResponse.json(
    { ...partial, asof: partial.asof ?? new Date().toISOString() },
    { status },
  );
}

async function loadSectorContext(): Promise<SectorContext> {
  if (sectorCache && Date.now() - sectorCache.at < CACHE_MS) {
    return sectorCache.data;
  }
  try {
    const report = await runSectorMoneyFlow(
      ["--source", "local", "--period", "3mo"],
      15_000,
    );
    const data = summarizeSectorFlow(report);
    sectorCache = { at: Date.now(), data };
    return data;
  } catch {
    return summarizeSectorFlow(null);
  }
}

async function loadEvents(now: Date): Promise<{
  events: MarketContextPayload["events"];
  source: NonNullable<MarketContextPayload["eventSource"]>;
}> {
  if (eventCache && Date.now() - eventCache.at < CACHE_MS) {
    return { events: eventCache.data, source: "lse" };
  }
  const end = new Date(now.getTime() + 60 * 86_400_000);
  try {
    const rows = await runLseEconomicCalendar({
      start: now.toISOString().slice(0, 10),
      end: end.toISOString().slice(0, 10),
      region: "US",
      limit: 250,
    });
    const events = marketEventsFromLse(rows, now, 8);
    if (events.length) {
      eventCache = { at: Date.now(), data: events };
      return { events, source: "lse" };
    }
  } catch {
    // The verified static schedule below keeps the shell useful during outages.
  }
  return {
    events: upcomingMarketEvents(now, 8),
    source: "verified_fallback",
  };
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const now = new Date();
  if (url.searchParams.get("format") === "ics") {
    const calendar = await loadEvents(now);
    return new Response(buildMarketCalendarIcs(now, calendar.events), {
      status: 200,
      headers: {
        "Content-Type": "text/calendar; charset=utf-8",
        "Content-Disposition": 'attachment; filename="trade-desk-market-events.ics"',
        "Cache-Control": "no-store",
      },
    });
  }

  const asof = now.toISOString();
  const [calendar, sectors] = await Promise.all([
    loadEvents(now),
    loadSectorContext(),
  ]);
  const payload: MarketContextPayload = {
    asof,
    events: calendar.events,
    eventSource: calendar.source,
    sectors,
  };
  return envelope({ ok: true, command: "market-context", data: payload, asof });
}
