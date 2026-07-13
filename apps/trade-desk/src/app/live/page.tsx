"use client";

import Link from "next/link";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { LiveDesk } from "@/components/live/LiveDesk";
import { OptionsDesk } from "@/components/options/OptionsDesk";
import { PageHeader } from "@/components/shell/PageHeader";
import { liveHref, optionsHref } from "@/lib/routes";

type LiveMode = "risk" | "options";

const TABS: { key: LiveMode; label: string }[] = [
  { key: "risk", label: "Risk Mode" },
  { key: "options", label: "Options Structure" },
];

function LiveOptionsHub() {
  const searchParams = useSearchParams();
  const rawMode = searchParams.get("mode");
  const mode: LiveMode = rawMode === "options" ? "options" : "risk";
  const symbol = searchParams.get("symbol")?.toUpperCase() ?? "";

  return (
    <div className="td-page">
      <PageHeader
        title="Live / Options"
        description="Risk mode ticket and options structure side by side."
        meta={
          symbol ? (
            <span className="tabular" style={{ fontFamily: "var(--td-font-mono)" }}>
              {symbol}
            </span>
          ) : null
        }
        actions={
          <nav
            className="flex flex-wrap gap-1 border-b border-[var(--td-ink-700)]"
            role="tablist"
            aria-label="Live desk"
          >
            {TABS.map((t) => {
              const active = mode === t.key;
              const href = t.key === "risk" ? liveHref(symbol) : optionsHref(symbol);
              return (
                <Link
                  key={t.key}
                  href={href}
                  role="tab"
                  aria-selected={active}
                  aria-controls={`live-panel-${t.key}`}
                  className={`td-btn ${active ? "td-btn-primary" : "td-btn-ghost"}`}
                >
                  {t.label}
                </Link>
              );
            })}
          </nav>
        }
      />

      <div
        id={`live-panel-${mode}`}
        role="tabpanel"
        className="flex flex-col gap-4"
        aria-label={TABS.find((t) => t.key === mode)?.label}
      >
        {mode === "risk" ? <LiveDesk showHeader={false} /> : <OptionsDesk showHeader={false} />}
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
          <p className="td-muted">Loading live desk…</p>
        </div>
      }
    >
      <LiveOptionsHub />
    </Suspense>
  );
}
