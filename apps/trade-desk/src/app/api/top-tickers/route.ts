import { NextResponse } from "next/server";

import type { FlowFeedEntry, OptionsFlowFeed } from "@/lib/flowFeed";
import type { ApiEnvelope, TopTickerCategory, TopTickerRow, TopTickersResponse } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 120;

const DEFAULT_LIMIT = 15;

function envelope<T>(
  partial: Omit<ApiEnvelope<T>, "asof"> & { asof?: string },
  status: number,
): NextResponse {
  const body: ApiEnvelope<T> = {
    ...partial,
    asof: partial.asof ?? new Date().toISOString(),
  };
  return NextResponse.json(body, { status });
}

function isCall(right: string | undefined): boolean {
  const u = (right ?? "").toUpperCase();
  return u === "C" || u === "CALL";
}

function aggregateTopTickers(entries: FlowFeedEntry[]): TopTickerRow[] {
  const map = new Map<string, Omit<TopTickerRow, "rank" | "sentiment" | "bullish_pct">>();

  for (const e of entries) {
    const symbol = (e.symbol ?? "").toUpperCase();
    if (!symbol) continue;
    const existing = map.get(symbol);
    const premium = e.premium ?? 0;
    const score = Number.isFinite(e.score) ? (e.score as number) : 0;
    const volume = Number.isFinite(e.volume) ? (e.volume as number) : 0;
    const call = isCall(e.right);
    const shortDte = Number.isFinite(e.dte) && (e.dte as number) <= 14;
    const mny = e.moneyness_pct ?? 0;
    const otm = Math.abs(mny) >= 0.03;

    if (existing) {
      existing.total_premium += premium;
      existing.total_volume += volume;
      existing.total_score += score;
      existing.max_score = Math.max(existing.max_score, score);
      existing.flag_count += 1;
      existing.short_dte_premium += shortDte ? premium : 0;
      existing.otm_premium += otm ? premium : 0;
      if (call) {
        existing.call_premium += premium;
        existing.call_count += 1;
      } else {
        existing.put_premium += premium;
        existing.put_count += 1;
      }
    } else {
      map.set(symbol, {
        symbol,
        total_premium: premium,
        call_premium: call ? premium : 0,
        put_premium: call ? 0 : premium,
        call_count: call ? 1 : 0,
        put_count: call ? 0 : 1,
        flag_count: 1,
        total_volume: volume,
        total_score: score,
        avg_score: score,
        max_score: score,
        short_dte_premium: shortDte ? premium : 0,
        otm_premium: otm ? premium : 0,
      });
    }
  }

  const rows: TopTickerRow[] = [];
  for (const raw of map.values()) {
    const total = raw.total_premium || 1;
    const bullishPct = (raw.call_premium / total) * 100;
    let sentiment: TopTickerRow["sentiment"] = "neutral";
    if (bullishPct >= 58) sentiment = "bullish";
    else if (bullishPct <= 42) sentiment = "bearish";
    rows.push({
      ...raw,
      avg_score: raw.flag_count > 0 ? raw.total_score / raw.flag_count : 0,
      sentiment,
      bullish_pct: Math.round(bullishPct * 10) / 10,
      rank: 0,
    });
  }
  return rows;
}

function buildCategories(rows: TopTickerRow[]): TopTickerCategory[] {
  const withRank = (sorted: TopTickerRow[]) =>
    sorted.map((r, i) => ({ ...r, rank: i + 1 }));

  const premium = withRank(
    [...rows].sort((a, b) => b.total_premium - a.total_premium),
  );
  const unusual = withRank(
    [...rows].sort((a, b) => b.total_score - a.total_score),
  );
  const active = withRank(
    [...rows].sort((a, b) => b.flag_count - a.flag_count),
  );
  const momentum = withRank(
    [...rows].sort(
      (a, b) =>
        b.short_dte_premium * (b.avg_score + 1) -
        a.short_dte_premium * (a.avg_score + 1),
    ),
  );

  return [
    {
      key: "premium",
      label: "Most Premium",
      description: "Highest total premium across calls and puts.",
      rows: premium,
    },
    {
      key: "unusual",
      label: "Most Unusual",
      description: "Largest aggregate unusual-activity score.",
      rows: unusual,
    },
    {
      key: "active",
      label: "Most Active",
      description: "Most flagged prints (sweep/block proxy when condition flags are unavailable).",
      rows: active,
    },
    {
      key: "momentum",
      label: "Short-Dated Momentum",
      description: "Urgent premium in contracts expiring within 14 days.",
      rows: momentum,
    },
  ];
}

type Body = {
  limit?: number | string;
  minPremium?: number | string;
};

async function loadFlowFeed(req: Request): Promise<OptionsFlowFeed | null> {
  const origin = new URL(req.url).origin;
  const res = await fetch(`${origin}/api/options-flow-feed`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!res.ok) return null;
  const json = (await res.json()) as ApiEnvelope<OptionsFlowFeed>;
  return json.data ?? null;
}

export async function POST(req: Request) {
  let body: Body = {};
  try {
    body = (await req.json()) as Body;
  } catch {
    // empty body is fine
  }

  const limitRaw = body.limit != null ? Number(body.limit) : DEFAULT_LIMIT;
  const limit = Number.isFinite(limitRaw) && limitRaw > 0 ? limitRaw : DEFAULT_LIMIT;
  const minPremiumRaw = body.minPremium != null ? Number(body.minPremium) : 0;
  const minPremium = Number.isFinite(minPremiumRaw) && minPremiumRaw >= 0 ? minPremiumRaw : 0;

  try {
    const feed = await loadFlowFeed(req);
    if (!feed) {
      return envelope<TopTickersResponse>(
        { ok: false, command: "top-tickers", error: "options flow feed unavailable" },
        502,
      );
    }

    const entries = (feed.entries ?? []).filter((e) => (e.premium ?? 0) >= minPremium);
    const rows = aggregateTopTickers(entries);
    const categories = buildCategories(rows).map((c) => ({
      ...c,
      rows: c.rows.slice(0, limit),
    }));

    const data: TopTickersResponse = {
      ok: true,
      categories,
      asof_utc: feed.asof_utc ?? new Date().toISOString(),
      note: "Aggregated from options flow flags. True sweep/block tags require OPRA condition codes.",
    };
    return envelope<TopTickersResponse>(
      { ok: true, command: "top-tickers", data, asof: data.asof_utc },
      200,
    );
  } catch (e) {
    return envelope<TopTickersResponse>(
      {
        ok: false,
        command: "top-tickers",
        error: e instanceof Error ? e.message : String(e),
      },
      502,
    );
  }
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const body: Body = {
    limit: url.searchParams.get("limit") || undefined,
    minPremium: url.searchParams.get("minPremium") || undefined,
  };
  const fakeReq = new Request(req.url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return POST(fakeReq);
}
