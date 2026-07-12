"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type NavLinkProps = {
  href: string;
  children: React.ReactNode;
  exact?: boolean;
};

export function NavLink({ href, children, exact = false }: NavLinkProps) {
  const pathname = usePathname();
  const active = exact
    ? pathname === href
    : pathname === href || pathname.startsWith(`${href}/`);

  return (
    <Link
      href={href}
      className={`td-nav-link${active ? " td-nav-link--active" : ""}`}
      aria-current={active ? "page" : undefined}
    >
      {children}
    </Link>
  );
}
