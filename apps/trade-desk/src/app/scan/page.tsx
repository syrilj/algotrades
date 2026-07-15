"use client";

import Link from "next/link";
import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { PicksDesk } from "@/components/picks/PicksDesk";
import { ScanDesk } from "@/components/scan/ScanDesk";
import SupplyChainDesk from "@/components/supply-chain/SupplyChainDesk";
import { HubTabs } from "@/components/shell/HubTabs";
import { PageHeader } from "@/components/shell/PageHeader";
import { watchHref } from "@/lib/routes";

export const dynamic = "force-dynamic";

type ScanView = "bias" | "picks" | "supply-chain";

const VIEWS: { key: ScanView; label: string }[] = [
  { key: "bias", label: "Market Bias" },
  { key: "picks", label: "Picks" },
  { key: "supply-chain", label: "Supply Chain" },
];

function resolveView(raw: string | null): ScanView {
  if (raw === "picks") return "picks";
  if (raw === "supply-chain") return "supply-chain";
  return "bias";
}

function ScanHub() {
  const params = useSearchParams();
  const router = useRouter();
  const rawView = params.get("view");

  // Legacy: Watch moved under Execution
  useEffect(() => {
    if (rawView === "watch") {
      router.replace(watchHref());
    }
  }, [rawView, router]);

  const view = resolveView(rawView);

  const tabs = VIEWS.map((item) => ({
    key: item.key,
    label: item.label,
    href: item.key === "bias" ? "/scan" : `/scan?view=${item.key}`,
  }));

  return (
    <div className="td-page">
      <PageHeader
        title="Radar"
        description="Market bias, sector picks, and supply-chain context. Watch board lives under Execution."
        meta={
          <span className="td-chip td-chip--warn">scan bias · live sizes</span>
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <HubTabs tabs={tabs} active={view} aria-label="Radar views" />
            <Link href={watchHref()} className="td-btn td-btn-ghost no-underline">
              Open Watch
            </Link>
          </div>
        }
      />

      <section
        id={`hub-panel-${view}`}
        role="tabpanel"
        className="td-hub-panel"
        aria-label={VIEWS.find((item) => item.key === view)?.label}
      >
        {view === "bias" ? <ScanDesk /> : null}
        {view === "picks" ? <PicksDesk showHeader={false} /> : null}
        {view === "supply-chain" ? <SupplyChainDesk /> : null}
      </section>
    </div>
  );
}

export default function ScanPage() {
  return (
    <Suspense
      fallback={
        <div className="td-page">
          <div className="td-panel p-3">Loading radar…</div>
        </div>
      }
    >
      <ScanHub />
    </Suspense>
  );
}
