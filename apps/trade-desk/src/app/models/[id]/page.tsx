"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import type { ApiEnvelope, ModelMetaConfig, ModelsCatalog } from "@/lib/types";
import { ModelBadges } from "@/components/leaderboard/ModelBadges";
import { ScoreBar } from "@/components/leaderboard/ScoreBar";
import { ModelFlow } from "@/components/models/ModelFlow";
import { ModelTuningView } from "@/components/models/ModelTuningView";
import { analyzeHref } from "@/lib/routes";

type ModelDetail = {
  id: string;
  has_engine: boolean;
  model_md: string | null;
  results: Record<string, unknown> | null;
  hypothesis: string | null;
  meta_config: ModelMetaConfig | null;
  is_default?: boolean;
  is_winner?: boolean;
  metrics?: {
    score?: number;
    win_rate?: number;
    sharpe?: number;
    profit_factor?: number;
    max_drawdown?: number;
    total_return?: number;
    trade_count?: number;
  };
};

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const body = (await res.json()) as ApiEnvelope<T> | T;
  if (body && typeof body === "object" && "ok" in body) {
    const env = body as ApiEnvelope<T>;
    if (!env.ok) throw new Error(env.error || "Request failed");
    return env.data as T;
  }
  return body as T;
}

function fmtPct(n: number | undefined, digits = 1): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}

function fmtNum(n: number | undefined, digits = 2): string {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toFixed(digits);
}

function pickMetrics(
  detail: ModelDetail,
): NonNullable<ModelDetail["metrics"]> {
  if (detail.metrics) return detail.metrics;
  const r = detail.results;
  if (!r || typeof r !== "object") return {};
  return {
    score: typeof r.score === "number" ? r.score : undefined,
    win_rate:
      typeof r.win_rate === "number"
        ? r.win_rate
        : typeof r.wr === "number"
          ? r.wr
          : undefined,
    sharpe: typeof r.sharpe === "number" ? r.sharpe : undefined,
    profit_factor:
      typeof r.profit_factor === "number" ? r.profit_factor : undefined,
    max_drawdown:
      typeof r.max_drawdown === "number" ? r.max_drawdown : undefined,
    total_return:
      typeof r.total_return === "number" ? r.total_return : undefined,
    trade_count:
      typeof r.trade_count === "number" ? r.trade_count : undefined,
  };
}

export default function ModelDetailPage() {
  const params = useParams<{ id: string }>();
  const id = decodeURIComponent(params?.id ?? "");
  const [detail, setDetail] = useState<ModelDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const [raw, catalog] = await Promise.all([
        fetchJson<ModelDetail>(`/api/models?id=${encodeURIComponent(id)}`),
        fetchJson<ModelsCatalog>("/api/models").catch(() => null),
      ]);
      setDetail({
        ...raw,
        is_default:
          raw.is_default ??
          Boolean(catalog && raw.id === catalog.default_model),
        is_winner:
          raw.is_winner ?? Boolean(catalog?.winner && raw.id === catalog.winner),
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load model");
      setDetail(null);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  const metrics = detail ? pickMetrics(detail) : {};
  const md = detail?.model_md || detail?.hypothesis || "";

  return (
    <main
      className="min-h-screen px-4 py-6 sm:px-6 max-w-5xl"
      style={{
        background: "var(--td-ink-950, #0B1014)",
        color: "var(--td-ink-100, #E2E8F0)",
        fontFamily: "var(--td-font-body, IBM Plex Sans, ui-sans-serif, system-ui, sans-serif)",
      }}
    >
      <nav className="mb-4 text-[13px]" style={{ color: "var(--td-ink-400, #64748B)" }}>
        <Link href="/leaderboard" className="hover:underline">
          ← Leaderboard
        </Link>
        <span className="mx-2">·</span>
        <Link href="/models" className="hover:underline">
          Models
        </Link>
      </nav>

      {loading ? (
        <p className="text-[13px]" style={{ color: "var(--td-ink-400, #64748B)" }}>
          Loading model…
        </p>
      ) : null}

      {error ? (
        <p
          className="text-[13px]"
          style={{ color: "var(--td-action-avoid, #A34848)" }}
          role="alert"
        >
          {error}
        </p>
      ) : null}

      {detail ? (
        <>
          <header className="mb-6">
            <h1
              className="text-[20px] font-medium"
              style={{
                fontFamily: "var(--td-font-mono, ui-monospace, Menlo, monospace)",
              }}
            >
              {detail.id}
            </h1>
            <div className="mt-2">
              <ModelBadges
                isWinner={detail.is_winner}
                isDefault={detail.is_default}
                hasEngine={detail.has_engine}
              />
            </div>
            <p
              className="text-[13px] mt-2"
              style={{ color: "var(--td-ink-400, #64748B)" }}
            >
              Default engine and Winner may differ — see catalog / WINNER.json.
            </p>
          </header>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <section
              className="p-4 rounded-sm"
              style={{
                background: "var(--td-ink-900, #12181F)",
                border: "1px solid var(--td-ink-700, #243040)",
              }}
            >
              <h2 className="text-[16px] mb-3">Metrics</h2>
              {metrics.score != null ? (
                <div className="mb-3">
                  <p
                    className="text-[12px] mb-1"
                    style={{ color: "var(--td-ink-400, #64748B)" }}
                  >
                    Score
                  </p>
                  <ScoreBar
                    value={metrics.score}
                    max={Math.max(1, metrics.score)}
                    winner={detail.is_winner}
                  />
                </div>
              ) : null}
              <dl className="grid grid-cols-2 gap-3 text-[13px]">
                {(
                  [
                    ["WR", fmtPct(metrics.win_rate)],
                    ["Sharpe", fmtNum(metrics.sharpe)],
                    ["PF", fmtNum(metrics.profit_factor)],
                    ["DD", fmtPct(metrics.max_drawdown)],
                    ["Ret", fmtPct(metrics.total_return)],
                    [
                      "Trades",
                      metrics.trade_count != null
                        ? String(metrics.trade_count)
                        : "—",
                    ],
                  ] as const
                ).map(([label, value]) => (
                  <div key={label}>
                    <dt
                      className="text-[11px]"
                      style={{ color: "var(--td-ink-400, #64748B)" }}
                    >
                      {label}
                    </dt>
                    <dd
                      className="tabular-nums"
                      style={{
                        fontFamily:
                          "var(--td-font-mono, ui-monospace, Menlo, monospace)",
                      }}
                    >
                      {value}
                    </dd>
                  </div>
                ))}
              </dl>
            </section>

            <section
              className="p-4 rounded-sm flex flex-col gap-3"
              style={{
                background: "var(--td-ink-900, #12181F)",
                border: "1px solid var(--td-ink-700, #243040)",
              }}
            >
              <h2 className="text-[16px]">Routing</h2>
              <p
                className="text-[13px]"
                style={{ color: "var(--td-ink-300, #94A3B8)" }}
              >
                Use this engine explicitly, or leave Analyze on{" "}
                <code className="text-[12px]">auto</code> to pick by symbol rank.
              </p>
              <div className="flex flex-col gap-2 mt-auto">
                <Link
                  href={analyzeHref({ model: detail.id })}
                  className="text-center text-[13px] py-2 rounded-sm"
                  style={{
                    background: "var(--td-brand, #2F6F7A)",
                    color: "var(--td-ink-100, #E2E8F0)",
                  }}
                >
                  Analyze with this model
                </Link>
                <Link
                  href="/leaderboard"
                  className="text-center text-[13px] py-2 rounded-sm"
                  style={{
                    border: "1px solid var(--td-ink-600, #334155)",
                    color: "var(--td-ink-200, #CBD5E1)",
                  }}
                >
                  Back to Leaderboard
                </Link>
              </div>
            </section>
          </div>

          <section
            className="p-4 rounded-sm mb-6"
            style={{
              background: "var(--td-ink-900, #12181F)",
              border: "1px solid var(--td-ink-700, #243040)",
            }}
          >
            <ModelFlow model={detail.id} />
          </section>

          <section
            className="p-4 rounded-sm mb-6"
            style={{
              background: "var(--td-ink-900, #12181F)",
              border: "1px solid var(--td-ink-700, #243040)",
            }}
          >
            <ModelTuningView id={detail.id} metaConfig={detail.meta_config} />
          </section>

          <section
            className="p-4 rounded-sm"
            style={{
              background: "var(--td-ink-900, #12181F)",
              border: "1px solid var(--td-ink-700, #243040)",
            }}
          >
            <h2 className="text-[16px] mb-3">MODEL.md</h2>
            {md ? (
              <pre
                className="whitespace-pre-wrap text-[13px] leading-relaxed max-h-[28rem] overflow-y-auto"
                style={{
                  color: "var(--td-ink-200, #CBD5E1)",
                  fontFamily:
                    "var(--td-font-mono, ui-monospace, Menlo, monospace)",
                }}
              >
                {md}
              </pre>
            ) : (
              <p
                className="text-[13px]"
                style={{ color: "var(--td-ink-400, #64748B)" }}
              >
                No MODEL.md / HYPOTHESIS.md found for this version.
              </p>
            )}
          </section>
        </>
      ) : null}
    </main>
  );
}
