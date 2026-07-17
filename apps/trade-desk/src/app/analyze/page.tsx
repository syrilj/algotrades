import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

/**
 * Legacy `/analyze` path — deep-links from older UI and bookmarks.
 * Analyze lives at `/command`; preserve query (symbol, model).
 */
export default async function AnalyzeRedirectPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(sp)) {
    if (value == null) continue;
    if (Array.isArray(value)) {
      for (const v of value) params.append(key, v);
    } else {
      params.set(key, value);
    }
  }
  const qs = params.toString();
  redirect(qs ? `/command?${qs}` : "/command");
}
