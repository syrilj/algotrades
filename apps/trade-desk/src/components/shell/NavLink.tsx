"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type NavLinkProps = {
  href: string;
  children: React.ReactNode;
  exact?: boolean;
  className?: string;
  onClick?: () => void;
};

export function NavLink({
  href,
  children,
  exact = false,
  className = "",
  onClick,
}: NavLinkProps) {
  const pathname = usePathname();
  const pathOnly = href.split("?")[0] || href;
  const active = exact
    ? pathname === pathOnly
    : pathname === pathOnly || pathname.startsWith(`${pathOnly}/`);

  const classes = ["td-nav-link", className, active ? "td-nav-link--active" : ""]
    .filter(Boolean)
    .join(" ");

  return (
    <Link
      href={href}
      className={classes}
      aria-current={active ? "page" : undefined}
      onClick={onClick}
    >
      {children}
    </Link>
  );
}
