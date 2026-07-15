import { redirect } from "next/navigation";

/** Legacy `/picks` — picks live under Radar. */
export default function PicksCompatibilityPage() {
  redirect("/scan?view=picks");
}
