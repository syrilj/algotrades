"use client";

import Link from "next/link";
import { Search } from "lucide-react";
import { NavLink } from "./NavLink";

const NAV = [
  { href: "/", label: "Analyze", exact: true },
  { href: "/scan", label: "Scan" },
  { href: "/live", label: "Live" },
  { href: "/positions", label: "Positions" },
  { href: "/research", label: "Research" },
] as const;

const LEGACY_NAV = [
  { href: "/supply-chain", label: "Supply chain" },
  { href: "/options", label: "Options" },
  { href: "/watch", label: "Watch" },
  { href: "/picks", label: "Picks" },
  { href: "/portfolio", label: "Portfolio" },
  { href: "/leaderboard", label: "Leaderboard" },
  { href: "/evolve", label: "Evolve" },
  { href: "/models", label: "Models" },
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
      <summary>More</summary>
      <div className="td-legacy-menu__list">
        <span className="td-legacy-menu__label">Legacy desk</span>
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
              {item.label}
            </NavLink>
          ))}
        </nav>

        <LegacyMenu />
        <TickerSearch />

        <div className="td-topbar-status" aria-label="Desk and market status">
          <span className="td-status-item">
            <span className="td-status-dot" aria-hidden="true" />
            <span className="td-status-label">Desk</span>
            <strong>Ready</strong>
          </span>
          <span className="td-status-divider" aria-hidden="true" />
          <span className="td-status-item">
            <span className="td-status-label">Market</span>
            <strong>Check live</strong>
          </span>
        </div>
      </header>

      <main className="td-main">{children}</main>

      <nav className="td-nav td-nav--mobile" aria-label="Mobile primary">
        {NAV.map((item) => (
          <div key={item.href} className="td-nav-mobile-item">
            <NavLink
              href={item.href}
              exact={"exact" in item && item.exact}
            >
              {item.label}
            </NavLink>
          </div>
        ))}
      </nav>
    </div>
  );
}
