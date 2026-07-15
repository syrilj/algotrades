import Link from "next/link";
import {
  Crosshair,
  Microscope,
  Radio,
  WalletCards,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type QuickAction = {
  id: string;
  href: string;
  label: string;
  detail: string;
  icon: LucideIcon;
};

const DEFAULT_ACTIONS: QuickAction[] = [
  {
    id: "analyze",
    href: "/",
    label: "Command",
    detail: "Analyze a symbol",
    icon: Crosshair,
  },
  {
    id: "live",
    href: "/live",
    label: "Execution",
    detail: "Discover · watch · decide",
    icon: Radio,
  },
  {
    id: "portfolio",
    href: "/positions",
    label: "Portfolio",
    detail: "Open risk · history",
    icon: WalletCards,
  },
  {
    id: "lab",
    href: "/research",
    label: "Lab",
    detail: "Models · evolve",
    icon: Microscope,
  },
];

export function QuickActionRail({
  actions = DEFAULT_ACTIONS,
}: {
  actions?: QuickAction[];
}) {
  return (
    <nav className="td-command-rail" aria-label="Quick actions">
      <span className="td-command-rail__label">Jump</span>
      <div className="td-command-rail__items">
        {actions.map((action) => {
          const Icon = action.icon;
          return (
            <Link
              className="td-command-action"
              href={action.href}
              key={action.id}
            >
              <span className="td-command-action__icon" aria-hidden="true">
                <Icon size={14} />
              </span>
              <span className="td-command-action__copy">
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
