"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";

import { PicksList } from "@/components/picks/PicksList";
import { PicksPanel, type PicksPanelValue } from "@/components/picks/PicksPanel";
import { ScanDesk } from "@/components/scan/ScanDesk";
import SupplyChainDesk from "@/components/supply-chain/SupplyChainDesk";
import { WatchBoard } from "@/components/watch/WatchBoard";
import { PageHeader } from "@/components/shell/PageHeader";

export const dynamic = "force-dynamic";

type ScanView = "bias" | "watch" | "picks" | "supply-chain";
const VIEWS: { key: ScanView; label: string; legacy?: string }[] = [
  { key: "bias", label: "Market Bias" },
  { key: "watch", label: "Watch List", legacy: "/watch" },
  { key: "picks", label: "Picks", legacy: "/picks" },
  { key: "supply-chain", label: "Supply Chain", legacy: "/supply-chain" },
];

function ScanHub() {
  const params = useSearchParams();
  const rawView = params.get("view");
  const view: ScanView = VIEWS.some((item) => item.key === rawView)
    ? (rawView as ScanView)
    : "bias";
  const [picks, setPicks] = useState<PicksPanelValue>({
    horizon: "day",
    model: "auto",
    sectors: ["mag7", "memory", "photonics"],
    symbols: "",
  });

  return (
    <div className="td-page">
      <PageHeader
        title="Scan hub"
        description="VPA + VWAP market bias, watch list, picks, and supply-chain context. Research bias only — size via Live adapt + paper ledger."
        meta={<span className="td-chip td-chip--warn">scan bias · live sizes</span>}
      />

      <nav className="mb-4 flex flex-wrap gap-1 border-b border-[var(--td-ink-700)]" aria-label="Scan views" role="tablist">
        {VIEWS.map((item) => {
          const selected = view === item.key;
          return (
            <Link
              key={item.key}
              href={item.key === "bias" ? "/scan" : `/scan?view=${item.key}`}
              className={`td-btn ${selected ? "td-btn-primary" : "td-btn-ghost"}`}
              role="tab"
              aria-selected={selected}
              aria-controls={`scan-panel-${item.key}`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>

      <section id={`scan-panel-${view}`} role="tabpanel" aria-label={VIEWS.find((item) => item.key === view)?.label}>
        {view === "bias" ? <ScanDesk /> : null}
        {view === "watch" ? (
          <div className="td-panel overflow-hidden">
            <WatchBoard
              rows={[]}
              emptyHint="No watch snapshot in this hub yet. Open the Watch desk to run the existing watch API; rows link to Analyze."
            />
            <div className="border-t border-[var(--td-ink-700)] p-3">
              <Link href="/watch" className="td-btn td-btn-primary">Open Watch desk</Link>
            </div>
          </div>
        ) : null}
        {view === "picks" ? (
          <div className="flex flex-col gap-3">
            <PicksPanel value={picks} models={[]} onChange={setPicks} onRun={() => window.location.assign("/picks")} />
            <div className="td-panel">
              <PicksList rows={[]} emptyHint="Run the existing Picks desk to query live setups; select a result to open Analyze." />
              <div className="border-t border-[var(--td-ink-700)] p-3">
                <Link href="/picks" className="td-btn td-btn-primary">Open Picks desk</Link>
              </div>
            </div>
          </div>
        ) : null}
        {view === "supply-chain" ? <SupplyChainDesk /> : null}
      </section>
    </div>
  );
}

export default function ScanPage() {
  return <Suspense fallback={<div className="td-page"><div className="td-panel p-3">Loading scan hub…</div></div>}><ScanHub /></Suspense>;
}
