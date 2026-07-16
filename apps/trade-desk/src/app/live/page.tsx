"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { ExecutionDesk } from "@/components/live/ExecutionDesk";
import { OptionsDesk } from "@/components/options/OptionsDesk";
import { WatchDesk } from "@/components/watch/WatchDesk";
import { GammaExposureDesk } from "@/components/gamma/GammaExposureDesk";
import { MoneyFlowDesk } from "@/components/money-flow/MoneyFlowDesk";
import { PicksDesk } from "@/components/picks/PicksDesk";
import { ScanDesk } from "@/components/scan/ScanDesk";
import SupplyChainDesk from "@/components/supply-chain/SupplyChainDesk";
import { HubTabs } from "@/components/shell/HubTabs";
import { PageHeader } from "@/components/shell/PageHeader";
import {
  hubPanelId,
  LIVE_MODE_DESCRIPTIONS,
  liveHubTabs,
  resolveLiveMode,
  type LiveMode,
} from "@/lib/routes";

const DISCOVER_MODES = new Set<LiveMode>([
  "bias",
  "flow",
  "picks",
  "supply-chain",
]);

function LiveOpsHub() {
  const searchParams = useSearchParams();
  const mode = resolveLiveMode(searchParams.get("mode"));
  const symbol = searchParams.get("symbol")?.trim().toUpperCase() ?? "";
  const accountRaw = Number(searchParams.get("account") || "1000");
  const account =
    Number.isFinite(accountRaw) && accountRaw > 0 ? accountRaw : 1000;

  const tabs = liveHubTabs(symbol || undefined, account);
  const activeLabel = tabs.find((t) => t.key === mode)?.label ?? "Decision";
  const phase = DISCOVER_MODES.has(mode) ? "Discover" : "Operate";
  const titleByMode: Record<LiveMode, string> = {
    bias: "Bias",
    flow: "Money flow",
    picks: "Picks",
    "supply-chain": "Supply chain",
    watch: "Watch",
    ticket: "Decision",
    options: "Options",
    gamma: "Gamma",
  };

  return (
    <div className="td-page">
      <PageHeader
        eyebrow={`Ops · ${phase}`}
        title={titleByMode[mode] ?? activeLabel}
        description={LIVE_MODE_DESCRIPTIONS[mode as LiveMode]}
        meta={
          symbol ? (
            <span
              className="tabular"
              style={{ fontFamily: "var(--td-font-mono)" }}
            >
              {symbol}
            </span>
          ) : (
            <span className="td-chip">bias · flow · picks · decision</span>
          )
        }
        actions={
          <HubTabs tabs={tabs} active={mode} aria-label="Ops workspace" />
        }
      />

      <div
        id={hubPanelId(mode)}
        role="tabpanel"
        className="td-hub-panel flex flex-col gap-4"
        aria-label={activeLabel}
      >
        {mode === "bias" ? <ScanDesk /> : null}
        {mode === "flow" ? <MoneyFlowDesk showHeader={false} /> : null}
        {mode === "picks" ? <PicksDesk showHeader={false} /> : null}
        {mode === "supply-chain" ? (
          <SupplyChainDesk showHeader={false} />
        ) : null}
        {mode === "ticket" ? <ExecutionDesk /> : null}
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
          <p className="td-muted">Loading ops desk…</p>
        </div>
      }
    >
      <LiveOpsHub />
    </Suspense>
  );
}
