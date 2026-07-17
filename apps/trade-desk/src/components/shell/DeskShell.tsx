"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ChevronLeft,
  Database,
  LayoutDashboard,
  Microscope,
  PanelLeft,
  Plus,
  Radio,
  Search,
  WalletCards,
  X,
} from "lucide-react";
import { MarketPulse } from "./MarketPulse";
import { MarketContext } from "./MarketContext";
import { NavLink } from "./NavLink";

/** Full-bleed marketing surfaces — no desk chrome. */
const BARE_PATHS = new Set(["/", "/welcome", "/privacy", "/terms"]);

const WORKSPACES = [
  {
    href: "/command",
    label: "Command",
    hint: "Analyze · verdict · size",
    exact: true,
    icon: LayoutDashboard,
  },
  {
    href: "/live",
    label: "Execution",
    hint: "Ticket · watch · options",
    exact: false,
    icon: Radio,
  },
  {
    href: "/positions",
    label: "Portfolio",
    hint: "Open book · risk",
    exact: false,
    icon: WalletCards,
  },
  {
    href: "/research",
    label: "Lab",
    hint: "Models · evolve · audit",
    exact: false,
    icon: Microscope,
  },
] as const;

const SYSTEMS = [
  { href: "/analysis-agent", label: "Analysis agent" },
  { href: "/live?mode=bias", label: "Bias scan" },
  { href: "/live?mode=flow", label: "Money flow" },
  { href: "/live?mode=picks", label: "Picks" },
  { href: "/live?mode=gamma", label: "Gamma" },
  { href: "/research?view=leaderboard", label: "Leaderboard" },
  { href: "/research?view=evolve", label: "Evolve farm" },
  { href: "/research?view=backtest", label: "Backtest" },
  { href: "/", label: "Product tour" },
] as const;

function TickerSearch() {
  return (
    <form
      className="td-ticker-search"
      action="/command"
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
      <label htmlFor="global-ticker-search" className="sr-only">
        Analyze ticker
      </label>
      <input
        id="global-ticker-search"
        name="symbol"
        type="search"
        placeholder="Analyze ticker…"
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

function DeskRail({
  collapsed,
  onToggle,
  onNavigate,
  showClose,
  operatorName,
  operatorInitials,
}: {
  collapsed: boolean;
  onToggle: () => void;
  onNavigate?: () => void;
  showClose?: boolean;
  operatorName: string;
  operatorInitials: string;
}) {
  const pathname = usePathname();

  return (
    <aside
      className={`td-rail${collapsed ? " td-rail--collapsed" : ""}`}
      aria-label="Desk navigation"
    >
      <div className="td-rail__head">
        {!collapsed ? (
          <>
            <Link href="/" className="td-brand" aria-label="Trade Desk home" onClick={onNavigate}>
              <span className="td-brand-mark">TD</span>
              <span className="td-brand-text">
                <span className="td-brand-trade">Trade</span>
                <span className="td-brand-desk">Desk</span>
              </span>
            </Link>
            {showClose ? (
              <button
                type="button"
                className="td-rail__collapse"
                onClick={onToggle}
                aria-label="Close navigation"
              >
                <X size={15} />
              </button>
            ) : (
              <button
                type="button"
                className="td-rail__collapse"
                onClick={onToggle}
                aria-label="Collapse sidebar"
              >
                <ChevronLeft size={15} />
              </button>
            )}
          </>
        ) : (
          <button
            type="button"
            className="td-brand-mark td-brand-mark--solo td-brand-mark--expand"
            onClick={onToggle}
            aria-label="Expand sidebar"
            title="Expand sidebar"
          >
            TD
          </button>
        )}
      </div>

      <div className="td-rail__cta-wrap">
        <Link
          href="/command"
          className="td-rail__cta"
          title="New analysis"
          onClick={onNavigate}
        >
          <Plus size={16} aria-hidden="true" />
          {!collapsed ? <span>New analysis</span> : null}
        </Link>
      </div>

      <div className="td-rail__scroll">
        <section className="td-rail__section">
          {!collapsed ? <h2 className="td-rail__section-label">Workspaces</h2> : null}
          <nav className="td-rail__workspaces" aria-label="Primary">
            {WORKSPACES.map((item) => (
              <NavLink
                key={item.href}
                href={item.href}
                exact={item.exact}
                className="td-rail__item"
                onClick={onNavigate}
              >
                <item.icon className="td-rail__item-icon" size={16} aria-hidden="true" />
                {!collapsed ? (
                  <span className="td-rail__item-copy">
                    <span className="td-rail__item-label">{item.label}</span>
                    <span className="td-rail__item-hint">{item.hint}</span>
                  </span>
                ) : null}
              </NavLink>
            ))}
          </nav>
        </section>

        <section className="td-rail__section">
          {!collapsed ? <h2 className="td-rail__section-label">Systems</h2> : null}
          <div className="td-rail__list" role="list">
            {SYSTEMS.map((item) => {
              const pathOnly = item.href.split("?")[0] || item.href;
              const active =
                pathOnly === "/"
                  ? pathname === "/"
                  : pathname === pathOnly || pathname.startsWith(`${pathOnly}/`);
              return (
                <Link
                  key={item.href + item.label}
                  href={item.href}
                  role="listitem"
                  className={`td-rail__row${active ? " is-active" : ""}`}
                  title={item.label}
                  onClick={onNavigate}
                >
                  <span className="td-rail__row-label">{item.label}</span>
                  {!collapsed ? (
                    <span className="td-rail__row-dot" aria-hidden="true" />
                  ) : null}
                </Link>
              );
            })}
          </div>
        </section>
      </div>

      {!collapsed ? (
        <div className="td-rail__data" aria-label="Data contract">
          <div className="td-rail__data-row">
            <Database size={12} aria-hidden="true" />
            <span>Data contract</span>
          </div>
          <dl className="td-rail__data-meta">
            <div>
              <dt>Bars</dt>
              <dd>Local OHLCV</dd>
            </div>
            <div>
              <dt>Interval</dt>
              <dd>1H study</dd>
            </div>
            <div>
              <dt>Features</dt>
              <dd>Point-in-time</dd>
            </div>
            <div>
              <dt>Book</dt>
              <dd>Paper ledger</dd>
            </div>
          </dl>
        </div>
      ) : null}

      <div className="td-rail__foot">
        <Link
          className={`td-account${collapsed ? " td-account--icon" : ""}`}
          href="/profile"
          aria-label="Open operator profile"
          onClick={onNavigate}
        >
          <span className="td-account__avatar">{operatorInitials}</span>
          {!collapsed ? (
            <span className="td-account__copy">
              <span className="td-account__label">Operator profile</span>
              <strong>{operatorName}</strong>
            </span>
          ) : null}
        </Link>
      </div>
    </aside>
  );
}

export function DeskShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "/";
  const isBare = BARE_PATHS.has(pathname);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [operator, setOperator] = useState({ name: "Local operator", initials: "TD" });

  useEffect(() => {
    try {
      if (localStorage.getItem("td-sidebar-collapsed") === "true") {
        setIsCollapsed(true);
      }
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    const syncProfile = (event?: Event) => {
      try {
        const eventDetail = event instanceof CustomEvent ? event.detail as { displayName?: string; initials?: string } : null;
        const stored = window.localStorage.getItem("td-operator-profile-v1");
        const parsed = eventDetail ?? (stored ? JSON.parse(stored) as { displayName?: string; initials?: string } : null);
        if (parsed) {
          setOperator({
            name: parsed.displayName?.trim() || "Local operator",
            initials: parsed.initials?.trim().slice(0, 3).toUpperCase() || "TD",
          });
        }
      } catch {
        /* keep safe local defaults */
      }
    };
    syncProfile();
    window.addEventListener("td-profile-updated", syncProfile);
    return () => window.removeEventListener("td-profile-updated", syncProfile);
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!mobileOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [mobileOpen]);

  const toggleCollapse = () => {
    const next = !isCollapsed;
    setIsCollapsed(next);
    try {
      localStorage.setItem("td-sidebar-collapsed", String(next));
    } catch {
      /* ignore */
    }
  };

  if (isBare) {
    return (
      <div className="td-shell td-shell--bare">
        {children}
      </div>
    );
  }

  return (
    <div className="td-shell td-shell--grok">
      {/* Desktop rail */}
      <div className="td-rail-desktop" data-collapsed={isCollapsed ? "true" : "false"}>
        <DeskRail
          collapsed={isCollapsed}
          onToggle={toggleCollapse}
          operatorName={operator.name}
          operatorInitials={operator.initials}
        />
      </div>

      {/* Mobile drawer */}
      {mobileOpen ? (
        <button
          type="button"
          className="td-rail-scrim"
          aria-label="Close navigation"
          onClick={() => setMobileOpen(false)}
        />
      ) : null}
      <div
        className={`td-rail-mobile${mobileOpen ? " is-open" : ""}`}
        aria-hidden={!mobileOpen}
      >
        <DeskRail
          collapsed={false}
          onToggle={() => setMobileOpen(false)}
          onNavigate={() => setMobileOpen(false)}
          showClose
          operatorName={operator.name}
          operatorInitials={operator.initials}
        />
      </div>

      <div className="td-stage">
        <header className="td-topbar">
          <button
            type="button"
            className="td-topbar__menu"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation"
          >
            <PanelLeft size={18} />
          </button>

          <Link href="/" className="td-brand td-brand--mobile" aria-label="Trade Desk home">
            <span className="td-brand-mark">TD</span>
          </Link>

          <div className="td-topbar__search">
            <TickerSearch />
          </div>

          <div className="td-topbar-status">
            <MarketContext />
            <MarketPulse />
          </div>
        </header>

        <main className="td-main">{children}</main>
      </div>

      <nav className="td-nav td-nav--mobile" aria-label="Mobile primary">
        {WORKSPACES.map((item) => (
          <div key={item.href} className="td-nav-mobile-item">
            <NavLink href={item.href} exact={item.exact}>
              <item.icon className="td-nav-link__icon" size={16} aria-hidden="true" />
              <span className="td-nav-link__label">{item.label}</span>
            </NavLink>
          </div>
        ))}
      </nav>
    </div>
  );
}
