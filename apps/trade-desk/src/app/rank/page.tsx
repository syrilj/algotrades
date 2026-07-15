import { redirect } from "next/navigation";
import { researchHref } from "@/lib/routes";

/** Legacy `/rank` — model ranking lives under Lab → Leaderboard. */
export default function RankRedirectPage() {
  redirect(researchHref("leaderboard"));
}
