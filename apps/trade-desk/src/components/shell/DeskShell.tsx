"use client";

import Link from "next/link";
import { NavLink } from "./NavLink";

const NAV = [
  { href: "/", label: "Analyze", exact: true },
  { href: "/robust", label: "Robust" },
  { href: "/watch", label: "Watch" },
  { href: "/picks", label: "Picks" },
  { href: "/leaderboard", label: "Leaderboard" },
  { href: "/models", label: "Models" },
] as const;

export function DeskShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col" style={{ background: "var(--td-ink-950)" }}>
      <header
        className="sticky top-0 z-40 flex h-11 shrink-0 items-center gap-6 border-b px-4"
        style={{
          background: "var(--td-ink-900)",
          borderColor: "var(--td-ink-700)",
        }}
      >
        <Link
          href="/"
          className="flex shrink-0 items-baseline gap-1.5 no-underline"
          aria-label="Trade Desk home"
        >
          <span
            className="inline-flex h-5 w-5 items-center justify-center text-[10px] font-semibold"
            style={{
              background: "var(--td-ink-800)",
              border: "1px solid var(--td-ink-600)",
              borderRadius: "var(--td-radius-sm)",
              color: "var(--td-brand)",
              fontFamily: "var(--td-font-mono)",
            }}
          >
            TD
          </span>
          <span style={{ color: "var(--td-ink-200)", fontSize: "14px" }}>
            Trade
          </span>
          <span
            style={{
              color: "var(--td-ink-50)",
              fontSize: "14px",
              fontWeight: 600,
            }}
          >
            Desk
          </span>
        </Link>

        <nav
          className="hidden items-center gap-0.5 sm:flex"
          aria-label="Primary"
        >
          {NAV.map((item) => (
            <NavLink key={item.href} href={item.href} exact={"exact" in item && item.exact}>
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>

      <main className="flex-1 pb-14 sm:pb-0">{children}</main>

      <nav
        className="fixed inset-x-0 bottom-0 z-40 flex h-12 items-stretch border-t sm:hidden"
        style={{
          background: "var(--td-ink-900)",
          borderColor: "var(--td-ink-700)",
        }}
        aria-label="Mobile primary"
      >
        {NAV.map((item) => (
          <div key={item.href} className="flex flex-1 items-center justify-center">
            <NavLink href={item.href} exact={"exact" in item && item.exact}>
              {item.label}
            </NavLink>
          </div>
        ))}
      </nav>
    </div>
  );
}
