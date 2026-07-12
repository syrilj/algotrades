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
      className="relative px-2.5 py-1.5 text-[12px] font-medium tracking-wide transition-colors duration-[var(--td-dur-fast)]"
      style={{
        color: active ? "var(--td-brand)" : "var(--td-ink-300)",
      }}
      aria-current={active ? "page" : undefined}
    >
      {children}
      {active ? (
        <span
          aria-hidden
          className="absolute inset-x-2 -bottom-px h-px"
          style={{ background: "var(--td-brand)" }}
        />
      ) : null}
    </Link>
  );
}
