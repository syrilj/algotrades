"use client";

/**
 * Shared bordered pill. Background is a `color-mix` tint of `colorVar` —
 * NOT string concatenation (`${colorVar}22`), which produces invalid CSS
 * when `colorVar` is a `var(...)` reference. See OptionsDesk's old
 * `ModeBadge` for the bug this replaces.
 */
export function Chip({ label, colorVar, title }: { label: string; colorVar: string; title?: string }) {
  return (
    <span
      title={title}
      className="inline-flex items-center px-2 py-1 text-[12px] font-semibold tracking-wide"
      style={{
        color: colorVar,
        background: `color-mix(in srgb, ${colorVar} 22%, transparent)`,
        border: `1px solid ${colorVar}`,
        borderRadius: "var(--td-radius-sm)",
      }}
    >
      {label}
    </span>
  );
}
