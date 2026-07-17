"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { LeaderboardView } from "@/components/leaderboard/LeaderboardView";
import { ModelsCatalogView } from "@/components/models/ModelsCatalogView";
import { BacktestPanel } from "@/components/backtest/BacktestPanel";
import { EvolveDesk } from "@/components/evolve/EvolveDesk";
import { HubTabs } from "@/components/shell/HubTabs";
import { PageHeader } from "@/components/shell/PageHeader";
import {
  hubPanelId,
  researchHubTabs,
  resolveResearchView,
  type ResearchView,
} from "@/lib/routes";

function ResearchHubInner() {
  const searchParams = useSearchParams();
  const symbol = searchParams.get("symbol")?.trim().toUpperCase() ?? "";
  const view: ResearchView = resolveResearchView(searchParams.get("view"));
  const tabs = researchHubTabs(symbol || undefined);
  const activeLabel = tabs.find((t) => t.key === view)?.label ?? "Leaderboard";

  return (
    <div className="td-page">
      <PageHeader
        eyebrow="Desk"
        title="Lab"
        description="Leaderboard, model catalog, evolution farm, and backtest — all model research in one workspace."
        meta={
          symbol ? (
            <span className="tabular" style={{ fontFamily: "var(--td-font-mono)" }}>
              {symbol}
            </span>
          ) : (
            <span className="td-chip">leaderboard · models · evolve · backtest</span>
          )
        }
        actions={
          <HubTabs tabs={tabs} active={view} aria-label="Lab workspace" />
        }
      />

      <div
        id={hubPanelId(view)}
        role="tabpanel"
        className="td-hub-panel flex flex-col gap-4"
        aria-label={activeLabel}
      >
        {view === "leaderboard" ? (
          <LeaderboardView showHeader={false} />
        ) : view === "models" ? (
          <ModelsCatalogView showHeader={false} />
        ) : view === "evolve" ? (
          <EvolveDesk />
        ) : (
          <BacktestPanel showHeader={false} />
        )}
      </div>
    </div>
  );
}

export default function ResearchPage() {
  return (
    <Suspense
      fallback={
        <div className="td-page">
          <p className="td-muted">Loading lab workspace…</p>
        </div>
      }
    >
      <ResearchHubInner />
    </Suspense>
  );
}
