"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { LeaderboardView } from "@/components/leaderboard/LeaderboardView";
import { ModelsCatalogView } from "@/components/models/ModelsCatalogView";
import { BacktestPanel } from "@/components/backtest/BacktestPanel";
import { EvolveDesk } from "@/components/evolve/EvolveDesk";
import { HubTabs } from "@/components/shell/HubTabs";
import { PageHeader } from "@/components/shell/PageHeader";

type ResearchView = "leaderboard" | "models" | "evolve" | "backtest";

const TABS: { key: ResearchView; label: string }[] = [
  { key: "leaderboard", label: "Leaderboard" },
  { key: "models", label: "Model Catalog" },
  { key: "evolve", label: "Evolve Farm" },
  { key: "backtest", label: "Backtest" },
];

function ResearchHubInner() {
  const searchParams = useSearchParams();
  const rawView = searchParams.get("view");
  const view: ResearchView = TABS.some((t) => t.key === rawView)
    ? (rawView as ResearchView)
    : "leaderboard";

  return (
    <div className="td-page">
      <PageHeader
        title="Research"
        description="Leaderboard, model catalog, evolution farm, and backtest — all model research in one workspace."
      />

      <HubTabs
        tabs={TABS.map((t) => ({
          key: t.key,
          label: t.label,
          href: `/research?view=${t.key}`,
        }))}
        active={view}
        aria-label="Research workspace"
      />

      <div
        id={`hub-panel-${view}`}
        role="tabpanel"
        className="td-hub-panel flex flex-col gap-4"
        aria-label={TABS.find((t) => t.key === view)?.label}
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
          <p className="td-muted">Loading research workspace…</p>
        </div>
      }
    >
      <ResearchHubInner />
    </Suspense>
  );
}
