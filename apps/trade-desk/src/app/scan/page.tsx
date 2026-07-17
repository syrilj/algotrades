import { redirect } from "next/navigation";
import { liveHref, resolveScanView } from "@/lib/routes";

/**
 * Legacy `/scan` (Radar hub) — discovery now lives under Execution/Ops.
 * Preserve view + symbol so bookmarks keep working.
 */
export default async function ScanCompatibilityPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const sp = await searchParams;
  const rawView = typeof sp.view === "string" ? sp.view : null;
  // Legacy: Watch already moved under Execution
  const mode =
    rawView === "watch"
      ? "watch"
      : resolveScanView(rawView);
  const symbol =
    typeof sp.symbol === "string" ? sp.symbol.trim().toUpperCase() : "";
  redirect(liveHref(symbol || undefined, mode));
}
