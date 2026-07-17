import { redirect } from "next/navigation";
import { liveHref } from "@/lib/routes";

/** Legacy `/supply-chain` — supply chain lives under Ops (Execution) Discover. */
export default async function SupplyChainCompatibilityPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const sp = await searchParams;
  const symbol =
    typeof sp.symbol === "string" ? sp.symbol.trim().toUpperCase() : "";
  redirect(liveHref(symbol || undefined, "supply-chain"));
}
