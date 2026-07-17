import { NextResponse } from "next/server";
import { spawn } from "child_process";

import {
  buildMarketPulseSeries,
  finiteOrNull,
  type FearGreedRaw,
  type MarketPulsePayload,
  type RawQuote,
} from "@/lib/marketPulse";
import { pythonBin, repoRoot } from "@/lib/paths";
import type { ApiEnvelope } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 30;

/** In-process cache so the topbar can poll without thrashing yfinance. */
let cache: { at: number; payload: MarketPulsePayload } | null = null;
const CACHE_MS = 60_000;

function envelope(
  partial: Omit<ApiEnvelope<MarketPulsePayload>, "asof"> & { asof?: string },
  status: number,
): NextResponse {
  const body: ApiEnvelope<MarketPulsePayload> = {
    ...partial,
    asof: partial.asof ?? new Date().toISOString(),
  };
  return NextResponse.json(body, { status });
}

/**
 * Fetch last + previous close for a few symbols via yfinance in one short
 * Python process. Graceful: returns {} on failure so the UI can show "—".
 */
function fetchQuotesPython(
  symbols: string[],
  timeoutMs = 12_000,
): Promise<Record<string, { last: number | null; prev: number | null }>> {
  const py = pythonBin();
  const code = `
import json, sys
try:
    import yfinance as yf
except Exception as e:
    print(json.dumps({"ok": False, "error": str(e)}))
    sys.exit(0)
syms = ${JSON.stringify(symbols)}
out = {}
for s in syms:
    last = None
    prev = None
    try:
        t = yf.Ticker(s)
        h = t.history(period="5d", auto_adjust=True)
        if h is not None and len(h) > 0:
            closes = h["Close"].dropna()
            if len(closes) > 0:
                last = float(closes.iloc[-1])
            if len(closes) > 1:
                prev = float(closes.iloc[-2])
    except Exception:
        pass
    out[s] = {"last": last, "prev": prev}
print(json.dumps({"ok": True, "quotes": out}))
`;
  return new Promise((resolve) => {
    const child = spawn(py, ["-c", code], {
      cwd: repoRoot(),
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    });
    let stdout = "";
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      resolve({});
    }, timeoutMs);
    child.stdout.on("data", (d: Buffer) => {
      stdout += d.toString();
    });
    child.on("error", () => {
      clearTimeout(timer);
      resolve({});
    });
    child.on("close", () => {
      clearTimeout(timer);
      try {
        const start = stdout.indexOf("{");
        if (start < 0) {
          resolve({});
          return;
        }
        const parsed = JSON.parse(stdout.slice(start)) as {
          ok?: boolean;
          quotes?: Record<string, { last?: number | null; prev?: number | null }>;
        };
        const quotes = parsed.quotes ?? {};
        const mapped: Record<string, { last: number | null; prev: number | null }> = {};
        for (const [k, v] of Object.entries(quotes)) {
          mapped[k] = {
            last: finiteOrNull(v?.last),
            prev: finiteOrNull(v?.prev),
          };
        }
        resolve(mapped);
      } catch {
        resolve({});
      }
    });
  });
}

async function fetchFearGreed(timeoutMs = 8_000): Promise<FearGreedRaw> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    // Public free endpoint — no key. Value is 0–100.
    const res = await fetch("https://api.alternative.me/fng/?limit=1&format=json", {
      signal: controller.signal,
      headers: { Accept: "application/json" },
      next: { revalidate: 0 },
    });
    if (!res.ok) return { value: null, source: "alternative.me" };
    const json = (await res.json()) as {
      data?: Array<{ value?: string; value_classification?: string }>;
    };
    const row = json.data?.[0];
    return {
      value: finiteOrNull(row?.value),
      classification: row?.value_classification ?? null,
      source: "alternative.me",
    };
  } catch {
    return { value: null, source: "alternative.me" };
  } finally {
    clearTimeout(timer);
  }
}

export async function GET() {
  if (cache && Date.now() - cache.at < CACHE_MS) {
    return envelope(
      { ok: true, command: "market-pulse", data: cache.payload, asof: cache.payload.asof },
      200,
    );
  }

  try {
    const [quotes, fearGreed] = await Promise.all([
      fetchQuotesPython(["^VIX", "CL=F"]),
      fetchFearGreed(),
    ]);

    const vixRaw = quotes["^VIX"];
    const oilRaw = quotes["CL=F"];

    const vix: RawQuote | null = vixRaw
      ? {
          symbol: "^VIX",
          last: vixRaw.last,
          prevClose: vixRaw.prev,
          source: "yfinance",
        }
      : null;
    const oil: RawQuote | null = oilRaw
      ? {
          symbol: "CL=F",
          last: oilRaw.last,
          prevClose: oilRaw.prev,
          source: "yfinance",
        }
      : null;

    const payload = buildMarketPulseSeries({
      vix,
      oil,
      fearGreed,
      asof: new Date().toISOString(),
    });

    cache = { at: Date.now(), payload };

    return envelope(
      {
        ok: true,
        command: "market-pulse",
        data: payload,
        asof: payload.asof,
        // Surface partial failures without failing the shell.
        error: payload.ok ? undefined : payload.error ?? undefined,
      },
      200,
    );
  } catch (e) {
    const payload = buildMarketPulseSeries({
      asof: new Date().toISOString(),
    });
    payload.error = e instanceof Error ? e.message : String(e);
    return envelope(
      {
        ok: true,
        command: "market-pulse",
        data: payload,
        asof: payload.asof,
        error: payload.error ?? undefined,
      },
      200,
    );
  }
}
