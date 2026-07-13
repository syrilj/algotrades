import { redirect } from "next/navigation";

export default async function OptionsCompatibilityPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const sp = await searchParams;
  const symbol =
    typeof sp.symbol === "string" ? sp.symbol.trim().toUpperCase() : "";
  const target = symbol
    ? `/live?mode=options&symbol=${encodeURIComponent(symbol)}`
    : "/live?mode=options";
  redirect(target);
}
