"use client";

import { Suspense } from "react";
import { LeaderboardView } from "@/components/leaderboard/LeaderboardView";

export default function LeaderboardPage() {
  return (
    <Suspense
      fallback={
        <div className="td-page">
          <p className="td-muted">Loading leaderboard…</p>
        </div>
      }
    >
      <LeaderboardView showHeader />
    </Suspense>
  );
}
