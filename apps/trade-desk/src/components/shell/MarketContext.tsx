"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  BarChart3,
  BellRing,
  CalendarDays,
  ChevronDown,
  ExternalLink,
} from "lucide-react";

import {
  eventCountdown,
  eventDateLabel,
  type MarketContextPayload,
  type SectorContext,
} from "@/lib/marketContext";
import type { ApiEnvelope } from "@/lib/types";

const EMPTY_SECTORS: SectorContext = {
  tone: "unavailable",
  label: "Sector pulse",
  detail: "Loading rotation map",
  leader: null,
  laggard: null,
  moneyIn: [],
  moneyOut: [],
  definitive: false,
  confidence: null,
  asofBar: null,
};

function signedPct(value: number | null): string {
  if (value == null) return "—";
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;
}

export function MarketContext() {
  const [payload, setPayload] = useState<MarketContextPayload | null>(null);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    void fetch("/api/market-context", {
      cache: "no-store",
      signal: controller.signal,
    })
      .then((res) => res.json() as Promise<ApiEnvelope<MarketContextPayload>>)
      .then((json) => {
        if (!cancelled && json.data) setPayload(json.data);
      })
      .catch(() => {
        // Calendar and desk remain usable; this context is intentionally optional.
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, []);

  const events = payload?.events ?? [];
  const nextEvent = events[0];
  const sectors = payload?.sectors ?? EMPTY_SECTORS;

  return (
    <div className="td-market-context" aria-label="Market calendar and sector context">
      <details className="td-intel td-intel--calendar">
        <summary className="td-intel__trigger">
          <CalendarDays size={14} aria-hidden="true" />
          <span className="td-intel__eyebrow">Next risk</span>
          <strong>{nextEvent?.shortLabel ?? "Calendar"}</strong>
          <span className="td-intel__meta">
            {nextEvent ? eventCountdown(nextEvent.startsAt) : "loading"}
          </span>
          <ChevronDown className="td-intel__chevron" size={12} aria-hidden="true" />
        </summary>
        <div className="td-intel-popover td-intel-popover--calendar">
          <div className="td-intel-popover__head">
            <div>
              <span className="td-intel-popover__kicker">High-impact calendar</span>
              <h2>Know the volatility windows</h2>
            </div>
            <a
              className="td-intel-popover__action"
              href="/api/market-context?format=ics"
              download
            >
              <BellRing size={13} aria-hidden="true" />
              Add reminders
            </a>
          </div>
          <div className="td-event-list">
            {events.length ? (
              events.slice(0, 5).map((event, index) => (
                <a
                  key={event.id}
                  className={`td-event-row${index === 0 ? " is-next" : ""}`}
                  href={event.sourceUrl}
                  target="_blank"
                  rel="noreferrer"
                >
                  <span className="td-event-row__rail" aria-hidden="true" />
                  <span className="td-event-row__copy">
                    <span className="td-event-row__title">
                      <strong>{event.shortLabel}</strong>
                      {event.label}
                    </span>
                    <span>{event.note}</span>
                  </span>
                  <span className="td-event-row__when">
                    <strong>{eventDateLabel(event.startsAt)}</strong>
                    <span>{eventCountdown(event.startsAt)}</span>
                  </span>
                  <ExternalLink size={12} aria-hidden="true" />
                </a>
              ))
            ) : (
              <p className="td-intel-popover__empty">Loading the verified market calendar…</p>
            )}
          </div>
          <p className="td-intel-popover__foot">
            {payload?.eventSource === "lse"
              ? "Live LSE economic calendar · reminders fire one hour before."
              : "Verified Fed, BLS, and BEA fallback · reminders fire one hour before."}
          </p>
        </div>
      </details>

      <details className={`td-intel td-intel--sectors is-${sectors.tone}`}>
        <summary className="td-intel__trigger">
          <BarChart3 size={14} aria-hidden="true" />
          <span className="td-intel__eyebrow">Sectors</span>
          <strong>{sectors.label}</strong>
          <span className="td-intel__meta">{sectors.tone}</span>
          <ChevronDown className="td-intel__chevron" size={12} aria-hidden="true" />
        </summary>
        <div className="td-intel-popover td-intel-popover--sectors">
          <div className="td-intel-popover__head">
            <div>
              <span className="td-intel-popover__kicker">Sector sentiment</span>
              <h2>{sectors.detail}</h2>
            </div>
            <span className={`td-sector-regime is-${sectors.tone}`}>{sectors.tone}</span>
          </div>
          <div className="td-sector-sides">
            <div className="td-sector-side td-sector-side--in">
              <span>Leadership</span>
              <strong>{sectors.leader?.etf ?? "—"}</strong>
              <small>
                {sectors.leader?.name ?? "Scan unavailable"} · RS {signedPct(sectors.leader?.rs1d ?? null)}
              </small>
            </div>
            <div className="td-sector-side td-sector-side--out">
              <span>Weak sleeve</span>
              <strong>{sectors.laggard?.etf ?? "—"}</strong>
              <small>
                {sectors.laggard?.name ?? "Scan unavailable"} · RS {signedPct(sectors.laggard?.rs1d ?? null)}
              </small>
            </div>
          </div>
          <div className="td-sector-breadth">
            <span><i className="is-in" /> In: {sectors.moneyIn.join(" · ") || "—"}</span>
            <span><i className="is-out" /> Out: {sectors.moneyOut.join(" · ") || "—"}</span>
          </div>
          <div className="td-intel-popover__foot td-intel-popover__foot--action">
            <span>
              {sectors.asofBar ? `Bar ${sectors.asofBar}` : "Awaiting sector bar"}
              {sectors.confidence != null
                ? ` · ${Math.round(sectors.confidence * 100)}% rotation confidence`
                : ""}
            </span>
            <Link href="/live?mode=flow">Open full Flow board →</Link>
          </div>
        </div>
      </details>
    </div>
  );
}
