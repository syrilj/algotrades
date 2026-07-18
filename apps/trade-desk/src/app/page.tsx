import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { TradeDeskLandingClean } from "@/components/landing/TradeDeskLandingClean";

export const metadata: Metadata = {
  title: "Trade Desk — Research operator terminal for equity model paths",
  description:
    "Research workstation for studying causal equity models, volume structure, macro context, and paper risk tickets. Not investment advice. Not a live broker.",
};

type Sp = Record<string, string | string[] | undefined>;

/** Marketing landing is the home surface. Command desk lives at `/command`. */
export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<Sp>;
}) {
  const sp = await searchParams;
  // Preserve legacy deep-links: /?symbol=TSLA → /command?symbol=TSLA
  if (sp.symbol != null && String(sp.symbol).trim() !== "") {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(sp)) {
      if (value == null) continue;
      if (Array.isArray(value)) {
        for (const v of value) params.append(key, v);
      } else {
        params.set(key, value);
      }
    }
    redirect(`/command?${params.toString()}`);
  }

  return <TradeDeskLandingClean />;
}
