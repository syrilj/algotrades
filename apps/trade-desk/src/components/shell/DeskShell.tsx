"use client";

import Link from "next/link";
import { NavLink } from "./NavLink";

const NAV = [
  { href: "/", label: "Analyze", exact: true },
  { href: "/scan", label: "Scan" },
  { href: "/supply-chain", label: "Supply" },
  { href: "/live", label: "Live" },
  { href: "/options", label: "Options" },
  { href: "/watch", label: "Watch" },
  { href: "/picks", label: "Picks" },
  { href: "/positions", label: "Positions" },
  { href: "/portfolio", label: "Portfolio" },
  { href: "/leaderboard", label: "Leaderboard" },
  { href: "/evolve", label: "Evolve" },
  { href: "/models", label: "Models" },
] as const;

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

        <div className="td-topbar-status" aria-hidden>
          <span className="td-status-label">Session</span>
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
