import Link from "next/link";
import { ArrowUpRight, ScanSearch, TrendingUp } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type QuickAction = {
  id: string;
  href: string;
  label: string;
  detail: string;
  icon: LucideIcon;
};

const DEFAULT_ACTIONS: QuickAction[] = [
  { id: "analyze", href: "/", label: "Analyze a ticker", detail: "Open a symbol ticket", icon: ArrowUpRight },
  { id: "scan", href: "/scan", label: "Run a scan", detail: "Find active setups", icon: ScanSearch },
  { id: "live", href: "/live", label: "Open live desk", detail: "Monitor signals", icon: TrendingUp },
];

export function QuickActionRail({ actions = DEFAULT_ACTIONS }: { actions?: QuickAction[] }) {
  return (
    <nav className="td-command-rail" aria-label="Quick actions">
      <span className="td-command-rail__label">Quick actions</span>
      <div className="td-command-rail__items">
        {actions.map((action) => {
          const Icon = action.icon;
          return (
            <Link className="td-command-action" href={action.href} key={action.id}>
              <Icon size={14} aria-hidden="true" />
              <span>
                <strong>{action.label}</strong>
                <small>{action.detail}</small>
              </span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
