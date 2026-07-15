import { redirect } from "next/navigation";

export default async function GammaCompatibilityPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const sp = await searchParams;
  const symbol =
    typeof sp.symbol === "string" ? sp.symbol.trim().toUpperCase() : "";
  const target = symbol
    ? `/live?mode=gamma&symbol=${encodeURIComponent(symbol)}`
    : "/live?mode=gamma";
  redirect(target);
}
