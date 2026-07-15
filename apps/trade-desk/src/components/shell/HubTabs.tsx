"use client";

import Link from "next/link";

export type HubTab = {
  key: string;
  label: string;
  href: string;
  /** Optional mono count / badge shown after the label. */
  badge?: string | number;
};

type HubTabsProps = {
  tabs: readonly HubTab[];
  active: string;
  "aria-label": string;
};

/** Shared operator tab strip for Execution (Ops), Portfolio, and Lab hubs. */
export function HubTabs({
  tabs,
  active,
  "aria-label": ariaLabel,
}: HubTabsProps) {
  return (
    <nav className="td-hub-tabs" role="tablist" aria-label={ariaLabel}>
      {tabs.map((tab) => {
        const selected = tab.key === active;
        return (
          <Link
            key={tab.key}
            href={tab.href}
            role="tab"
            aria-selected={selected}
            aria-controls={`hub-panel-${tab.key}`}
            className={`td-hub-tab${selected ? " td-hub-tab--active" : ""}`}
            prefetch
          >
            <span className="td-hub-tab__label">{tab.label}</span>
            {tab.badge != null && tab.badge !== "" ? (
              <span className="td-hub-tab__badge">{tab.badge}</span>
            ) : null}
          </Link>
        );
      })}
    </nav>
  );
}
