"use client";

import { useEffect, useState } from "react";

import type { MarketPulsePayload, MarketPulseSeries } from "@/lib/marketPulse";
import type { ApiEnvelope } from "@/lib/types";

const POLL_MS = 90_000;

function toneClass(tone: MarketPulseSeries["tone"]): string {
  switch (tone) {
    case "up":
      return "td-pulse__chip--up";
    case "down":
      return "td-pulse__chip--down";
    case "unavailable":
      return "td-pulse__chip--na";
    default:
      return "td-pulse__chip--neutral";
  }
}

function PulseChip({ item }: { item: MarketPulseSeries }) {
  const title = [
    item.label,
    item.display !== "—" ? item.display : "unavailable",
    item.change && item.key !== "fear_greed" ? `Δ ${item.change}` : null,
    item.source ? `src ${item.source}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <span className={`td-pulse__chip ${toneClass(item.tone)}`} title={title}>
      <span className="td-pulse__label">{item.label}</span>
      <strong className="td-pulse__value tabular">{item.display}</strong>
      {item.change && item.key !== "fear_greed" && item.tone !== "unavailable" ? (
        <span className="td-pulse__change tabular">{item.change}</span>
      ) : null}
    </span>
  );
}

/**
 * Compact topbar market pulse: VIX · Fear & Greed · WTI oil.
 * Non-blocking: shell stays usable when quotes fail; shows "—" honestly.
 */
export function MarketPulse() {
  const [payload, setPayload] = useState<MarketPulsePayload | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function load() {
      try {
        const res = await fetch("/api/market-pulse", { cache: "no-store" });
        const json = (await res.json()) as ApiEnvelope<MarketPulsePayload>;
        if (!cancelled && json.data) {
          setPayload(json.data);
        } else if (!cancelled && !json.data) {
          // Keep previous payload if any; otherwise show empty unavailable series.
          setPayload((prev) =>
            prev ?? {
              asof: new Date().toISOString(),
              ok: false,
              series: [
                { key: "vix", label: "VIX", display: "—", value: null, tone: "unavailable" },
                { key: "fear_greed", label: "F&G", display: "—", value: null, tone: "unavailable" },
                { key: "oil", label: "WTI", display: "—", value: null, tone: "unavailable" },
              ],
              error: json.error ?? "unavailable",
            },
          );
        }
      } catch {
        if (!cancelled) {
          setPayload((prev) =>
            prev ?? {
              asof: new Date().toISOString(),
              ok: false,
              series: [
                { key: "vix", label: "VIX", display: "—", value: null, tone: "unavailable" },
                { key: "fear_greed", label: "F&G", display: "—", value: null, tone: "unavailable" },
                { key: "oil", label: "WTI", display: "—", value: null, tone: "unavailable" },
              ],
              error: "fetch failed",
            },
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
        if (!cancelled) {
          timer = setTimeout(() => void load(), POLL_MS);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  const series = payload?.series ?? [
    { key: "vix", label: "VIX", display: loading ? "…" : "—", value: null, tone: "unavailable" as const },
    { key: "fear_greed", label: "F&G", display: loading ? "…" : "—", value: null, tone: "unavailable" as const },
    { key: "oil", label: "WTI", display: loading ? "…" : "—", value: null, tone: "unavailable" as const },
  ];

  return (
    <div
      className="td-pulse"
      aria-label="Market pulse"
      data-loading={loading ? "1" : "0"}
      data-ok={payload?.ok ? "1" : "0"}
    >
      {series.map((item) => (
        <PulseChip key={item.key} item={item} />
      ))}
    </div>
  );
}
