"use client";

import Link from "next/link";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { LeaderboardView } from "@/components/leaderboard/LeaderboardView";
import { ModelsCatalogView } from "@/components/models/ModelsCatalogView";
import { BacktestPanel } from "@/components/backtest/BacktestPanel";
import { EvolveDesk } from "@/components/evolve/EvolveDesk";
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

      <nav
        className="flex flex-wrap gap-1 border-b border-[var(--td-ink-700)]"
        role="tablist"
        aria-label="Research workspace"
      >
        {TABS.map((t) => {
          const active = view === t.key;
          return (
            <Link
              key={t.key}
              href={`/research?view=${t.key}`}
              role="tab"
              aria-selected={active}
              aria-controls={`research-panel-${t.key}`}
              className={`td-btn ${active ? "td-btn-primary" : "td-btn-ghost"}`}
            >
              {t.label}
            </Link>
          );
        })}
      </nav>

      <div
        id={`research-panel-${view}`}
        role="tabpanel"
        className="flex flex-col gap-4"
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
