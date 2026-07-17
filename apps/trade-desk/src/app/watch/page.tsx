import { redirect } from "next/navigation";

/**
 * Legacy `/watch` — watch board now lives under Execution.
 * Preserve query where useful (none required for board).
 */
export default function WatchCompatibilityPage() {
  redirect("/live?mode=watch");
}
