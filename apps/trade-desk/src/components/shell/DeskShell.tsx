"use client";

import Link from "next/link";
import {
  Activity,
  ChevronDown,
  LayoutDashboard,
  Microscope,
  Radio,
  ScanSearch,
  Search,
  WalletCards,
} from "lucide-react";
import { NavLink } from "./NavLink";

const NAV = [
  { href: "/", label: "Command", exact: true, icon: LayoutDashboard },
  { href: "/scan", label: "Radar", icon: ScanSearch },
  { href: "/live", label: "Execution", icon: Radio },
  { href: "/positions", label: "Portfolio", icon: WalletCards },
  { href: "/research", label: "Lab", icon: Microscope },
] as const;

/** Rare tools not already on primary hubs (Execution / Radar / Lab). */
const LEGACY_NAV = [
  { href: "/analysis-agent", label: "Analysis agent" },
  { href: "/evolve", label: "Evolve (direct)" },
  { href: "/robust", label: "Backtest (direct)" },
  { href: "/leaderboard", label: "Leaderboard (direct)" },
] as const;

function TickerSearch() {
  return (
    <form
      className="td-ticker-search"
      action="/"
      method="get"
      role="search"
      onSubmit={(event) => {
        const input = event.currentTarget.elements.namedItem("symbol");
        if (input instanceof HTMLInputElement) {
          input.value = input.value.trim().toUpperCase();
        }
      }}
    >
      <Search size={15} aria-hidden="true" />
      <label htmlFor="global-ticker-search">Analyze ticker</label>
      <input
        id="global-ticker-search"
        name="symbol"
        type="search"
        placeholder="Ticker (e.g. AAPL)"
        autoComplete="off"
        spellCheck={false}
        onChange={(event) => {
          event.currentTarget.value = event.currentTarget.value.toUpperCase();
        }}
      />
      <kbd>↵</kbd>
    </form>
  );
}

function LegacyMenu() {
  return (
    <details className="td-legacy-menu">
      <summary>Systems</summary>
      <div className="td-legacy-menu__list">
        <span className="td-legacy-menu__label">Specialized surfaces</span>
        {LEGACY_NAV.map((item) => (
          <NavLink key={item.href} href={item.href}>
            {item.label}
          </NavLink>
        ))}
      </div>
    </details>
  );
}

export function DeskShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="td-shell">
      <header className="td-topbar">
        <Link href="/" className="td-brand" aria-label="Trade Desk home">
          <span className="td-brand-mark">TD</span>
          <span className="td-brand-text">
            <span className="td-brand-trade">Trade</span>
            <span className="td-brand-desk">Desk</span>
          </span>
        </Link>

        <nav className="td-nav td-nav--desktop" aria-label="Primary">
          {NAV.map((item) => (
            <NavLink
              key={item.href}
              href={item.href}
              exact={"exact" in item && item.exact}
            >
              <item.icon size={15} aria-hidden="true" />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <LegacyMenu />
        <TickerSearch />

        <div className="td-topbar-status" aria-label="Desk and market status">
          <span className="td-status-item">
            <span className="td-status-dot" aria-hidden="true" />
            <span className="td-status-label">Mode</span>
            <strong>Local</strong>
          </span>
          <span className="td-status-divider" aria-hidden="true" />
          <span className="td-status-item">
            <Activity size={13} aria-hidden="true" />
            <span className="td-status-label">Data</span>
            <strong>On request</strong>
          </span>
        </div>

        <Link
          className="td-account"
          href="/positions"
          aria-label="Open positions and portfolio"
          data-auth-slot="clerk-user-button"
        >
          <span className="td-account__avatar">TD</span>
          <span className="td-account__copy">
            <span className="td-account__label">Workspace</span>
            <strong>Local operator</strong>
          </span>
          <ChevronDown size={14} aria-hidden="true" />
        </Link>
      </header>

      <main className="td-main">{children}</main>

      <nav className="td-nav td-nav--mobile" aria-label="Mobile primary">
        {NAV.map((item) => (
          <div key={item.href} className="td-nav-mobile-item">
            <NavLink
              href={item.href}
              exact={"exact" in item && item.exact}
            >
              <item.icon size={16} aria-hidden="true" />
              <span>{item.label}</span>
            </NavLink>
          </div>
        ))}
      </nav>
    </div>
  );
}
