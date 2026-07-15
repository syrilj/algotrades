"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { LiveDesk } from "@/components/live/LiveDesk";
import { OptionsDesk } from "@/components/options/OptionsDesk";
import { WatchDesk } from "@/components/watch/WatchDesk";
import { GammaExposureDesk } from "@/components/gamma/GammaExposureDesk";
import { HubTabs } from "@/components/shell/HubTabs";
import { PageHeader } from "@/components/shell/PageHeader";
import {
  gammaHref,
  liveHref,
  optionsHref,
  watchHref,
} from "@/lib/routes";

export type LiveMode = "ticket" | "watch" | "options" | "gamma";

function resolveMode(raw: string | null): LiveMode {
  if (raw === "watch") return "watch";
  if (raw === "options") return "options";
  if (raw === "gamma") return "gamma";
  // legacy aliases
  if (raw === "risk" || raw === "ticket" || !raw) return "ticket";
  return "ticket";
}

function LiveOptionsHub() {
  const searchParams = useSearchParams();
  const mode = resolveMode(searchParams.get("mode"));
  const symbol = searchParams.get("symbol")?.trim().toUpperCase() ?? "";

  const tabs = [
    { key: "ticket", label: "Ticket", href: liveHref(symbol || undefined) },
    { key: "watch", label: "Watch", href: watchHref() },
    {
      key: "options",
      label: "Options",
      href: optionsHref(symbol || undefined),
    },
    {
      key: "gamma",
      label: "Gamma",
      href: gammaHref(symbol || undefined),
    },
  ] as const;

  const descriptions: Record<LiveMode, string> = {
    ticket:
      "Risk ticket for one symbol — stand aside · equity hedge · options attack.",
    watch:
      "Multi-symbol operator board. Market scan ranks plays; poll keeps levels fresh. Click a name for a ticket.",
    options: "Options structure and attack paths for the selected symbol.",
    gamma: "Dealer gamma exposure — confirmation overlay for the model verdict.",
  };

  return (
    <div className="td-page">
      <PageHeader
        title="Execution"
        description={descriptions[mode]}
        meta={
          symbol ? (
            <span
              className="tabular"
              style={{ fontFamily: "var(--td-font-mono)" }}
            >
              {symbol}
            </span>
          ) : (
            <span className="td-chip">ticket · watch · options · gamma</span>
          )
        }
        actions={
          <HubTabs
            tabs={tabs}
            active={mode}
            aria-label="Execution workspace"
          />
        }
      />

      <div
        id={`hub-panel-${mode}`}
        role="tabpanel"
        className="td-hub-panel flex flex-col gap-4"
        aria-label={tabs.find((t) => t.key === mode)?.label}
      >
        {mode === "ticket" ? <LiveDesk showHeader={false} /> : null}
        {mode === "watch" ? <WatchDesk showHeader={false} /> : null}
        {mode === "options" ? <OptionsDesk showHeader={false} /> : null}
        {mode === "gamma" ? <GammaExposureDesk showHeader={false} /> : null}
      </div>
    </div>
  );
}

export const dynamic = "force-dynamic";

export default function LivePage() {
  return (
    <Suspense
      fallback={
        <div className="td-page">
          <p className="td-muted">Loading execution desk…</p>
        </div>
      }
    >
      <LiveOptionsHub />
    </Suspense>
  );
}
