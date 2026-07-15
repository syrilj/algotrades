import { redirect } from "next/navigation";
import { liveHref } from "@/lib/routes";

/** Legacy `/picks` — picks live under Ops (Execution) Discover. */
export default function PicksCompatibilityPage() {
  redirect(liveHref(undefined, "picks"));
}
