import { GexOiDesk } from "@/components/gex-oi/GexOiDesk";

export const dynamic = "force-dynamic";

export default async function GexOiPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const sp = await searchParams;
  const symbol =
    typeof sp.symbol === "string" ? sp.symbol.trim().toUpperCase() : "APLD";
  return <GexOiDesk symbol={symbol} showHeader />;
}
