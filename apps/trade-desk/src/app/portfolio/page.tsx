import { redirect } from "next/navigation";

/** Legacy `/portfolio` — portfolio builder lives under Positions hub. */
export default function PortfolioCompatibilityPage() {
  redirect("/positions?view=portfolio");
}
