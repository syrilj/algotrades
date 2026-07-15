"use client";

import { Play } from "lucide-react";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { PageHeader } from "@/components/shell/PageHeader";
import { actionColorClass, formatPct, formatUsd } from "@/lib/format";
import { analyzeHref } from "@/lib/routes";
import type { ApiEnvelope, ModelsCatalog, SupplyChainResponse } from "@/lib/types";
import Link from "next/link";
import { confColorVar, scoreRankClass } from "@/lib/actionColors";

export type SupplyChainFormValues = {
  symbol: string;
  account: number;
  riskPct: number;
  model: string;
};

function pct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return formatPct(n, 1);
}

function capLabel(cap: number | null | undefined): string {
  if (cap == null || cap <= 0) return "—";
  if (cap >= 1_000_000_000_000) return `${(cap / 1_000_000_000_000).toFixed(1)}T`;
  if (cap >= 1_000_000_000) return `${(cap / 1_000_000_000).toFixed(1)}B`;
  if (cap >= 1_000_000) return `${(cap / 1_000_000).toFixed(1)}M`;
  return `${cap}`;
}

function SupplyChainDeskInner() {
  const searchParams = useSearchParams();
  const qSymbol = searchParams.get("symbol")?.toUpperCase() ?? "";

  const [symbol, setSymbol] = useState(qSymbol || "NVDA");
  const [account, setAccount] = useState(100_000);
  const [riskPct, setRiskPct] = useState(0.5);
  const [model, setModel] = useState("auto");
  const [engines, setEngines] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SupplyChainResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (qSymbol) setSymbol(qSymbol);
  }, [qSymbol]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/models");
        const json = (await res.json()) as { ok?: boolean; data?: ModelsCatalog; error?: string };
        if (!res.ok || json.ok === false) throw new Error(json.error ?? `Models HTTP ${res.status}`);
        if (!cancelled) setEngines(json.data?.engines ?? []);
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const run = useCallback(async () => {
    const sym = symbol.trim().toUpperCase();
    if (!sym) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch("/api/supply-chain", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: sym,
          account,
          risk_pct: riskPct,
          model: model === "auto" ? undefined : model,
        }),
      });
      const json = (await res.json()) as ApiEnvelope<SupplyChainResponse>;
      if (!res.ok || json.ok === false || !json.data) {
        throw new Error(json.error ?? `Supply chain failed (${res.status})`);
      }
      setResult(json.data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Supply chain failed");
    } finally {
      setLoading(false);
    }
  }, [symbol, account, riskPct, model]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    run();
  };

  const anchor = result?.anchor;
  const suppliers = result?.suppliers ?? [];
  const top = suppliers.slice(0, 3);
  const anchorAction = anchor?.play?.action ?? "";

  return (
    <div className="td-page">
      <PageHeader
        title="Supply Chain"
        description="Enter a big-cap ticker. Discover its suppliers, read their growth sheets, measure correlation, and find the small-cap plays the big-cap move can pull."
        meta={
          result ? (
            <span className="tabular" style={{ fontFamily: "var(--td-font-mono)" }}>
              {result.symbol}
              {anchorAction ? <span style={{ color: "var(--td-ink-400)" }}> · {anchorAction}</span> : null}
            </span>
          ) : (
            <span>Seed a hardware mega-cap or any ticker with a web search</span>
          )
        }
      />

      <form onSubmit={handleSubmit} className="td-toolbar" aria-label="Supply chain controls">
        <div className="td-toolbar__row">
          <label className="td-field td-field--grow">
            <span className="td-label">Symbol</span>
            <input
              className="td-input tabular uppercase"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              placeholder="NVDA"
              autoComplete="off"
              spellCheck={false}
              required
              disabled={loading}
              style={{ fontFamily: "var(--td-font-mono)" }}
            />
          </label>
          <label className="td-field td-field--account">
            <span className="td-label">Account</span>
            <input
              className="td-input tabular"
              type="number"
              min={1000}
              step={1000}
              value={account}
              onChange={(e) => setAccount(Number(e.target.value))}
              disabled={loading}
              style={{ fontFamily: "var(--td-font-mono)" }}
            />
          </label>
          <label className="td-field td-field--risk">
            <span className="td-label">Risk %</span>
            <input
              className="td-input tabular"
              type="number"
              min={0.05}
              max={5}
              step={0.05}
              value={riskPct}
              onChange={(e) => setRiskPct(Number(e.target.value))}
              disabled={loading}
              style={{ fontFamily: "var(--td-font-mono)" }}
            />
          </label>
          <label className="td-field td-field--model">
            <span className="td-label">Model</span>
            <select
              className="td-input"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              disabled={loading}
              style={{ fontFamily: "var(--td-font-mono)" }}
            >
              <option value="auto">auto · best for symbol</option>
              {engines.map((id) => (
                <option key={id} value={id}>
                  {id}
                </option>
              ))}
            </select>
          </label>
          <button
            type="submit"
            className="td-btn td-btn-primary td-btn--run"
            disabled={loading || !symbol.trim()}
          >
            <Play size={14} strokeWidth={1.75} aria-hidden />
            {loading ? "Running…" : "Run"}
          </button>
        </div>
      </form>

      {error ? (
        <div className="td-alert td-alert--error" role="alert">
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="td-panel p-3">
          <p className="td-muted">Discovering suppliers, pulling fundamentals, and running models…</p>
        </div>
      ) : null}

      {anchor ? (
        <section className="td-panel p-3">
          <header className="td-page-header" style={{ marginBottom: 0 }}>
            <div className="td-page-header__main">
              <h2 className="td-page-title" style={{ fontSize: "var(--td-text-h2)" }}>
                Anchor: {anchor.symbol}
              </h2>
              <p className="td-page-desc" style={{ marginTop: 0 }}>
                {anchor.name} · {anchor.sector} / {anchor.industry || "—"}
              </p>
            </div>
            <div className="td-page-header__actions" style={{ alignItems: "flex-start" }}>
              <div className="tabular" style={{ textAlign: "right" }}>
                <div style={{ fontSize: "1.1rem", color: "var(--td-ink-50)" }}>
                  {formatUsd(anchor.price)}
                </div>
                <div className="td-muted" style={{ fontSize: "var(--td-text-caption)" }}>
                  cap {capLabel(anchor.market_cap)}
                </div>
              </div>
              {anchor.play ? (
                <span className={`td-chip ${actionColorClass(anchor.play.action)}`}>
                  {anchor.play.action}
                </span>
              ) : null}
            </div>
          </header>
          {anchor.play ? (
            <p className="td-muted" style={{ marginTop: "0.5rem" }}>
              {anchor.play.why}
            </p>
          ) : null}
        </section>
      ) : null}

      {top.length > 0 ? (
        <section>
          <h3 className="td-page-title" style={{ fontSize: "var(--td-text-h2)" }}>
            Top leads
          </h3>
          <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(16rem, 1fr))" }}>
            {top.map((s) => (
              <div key={s.symbol} className="td-panel p-3">
                <div className="flex items-center justify-between gap-2" style={{ marginBottom: "0.35rem" }}>
                  <Link
                    href={analyzeHref({ symbol: s.symbol })}
                    className="scan-sym"
                    style={{ fontSize: "1.05rem" }}
                  >
                    {s.symbol}
                  </Link>
                  <span className={`td-chip ${actionColorClass(s.play?.action)}`}>
                    {s.play?.action ?? "WAIT"}
                  </span>
                </div>
                <p className="td-muted" style={{ marginBottom: "0.35rem" }}>
                  {s.name} · {s.product || "supplier"}
                </p>
                <div className="flex gap-3 td-muted" style={{ fontSize: "var(--td-text-caption)" }}>
                  <span className="tabular">score {(s.score ?? 0).toFixed(2)}</span>
                  <span className="tabular">corr {pct(s.correlation_1y)}</span>
                  <span className="tabular">cap {capLabel(s.market_cap)}</span>
                  {s.is_small_cap ? <span style={{ color: "var(--td-action-breakout-watch)" }}>small cap</span> : null}
                </div>
                <p className="td-muted" style={{ marginTop: "0.5rem", fontSize: "0.78rem" }}>
                  {s.play?.do_next}
                </p>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {suppliers.length > 0 ? (
        <section>
          <h3 className="td-page-title" style={{ fontSize: "var(--td-text-h2)" }}>
            Supplier rank
          </h3>
          <div className="scan-table-wrap">
            <table className="scan-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Name / Product</th>
                  <th>Score</th>
                  <th>Action</th>
                  <th>Corr 1Y</th>
                  <th>Revenue YoY</th>
                  <th>FCF YoY</th>
                  <th>Cap</th>
                  <th>Source</th>
                  <th>Conf</th>
                </tr>
              </thead>
              <tbody>
                {suppliers.map((s) => (
                  <tr key={s.symbol}>
                    <td>
                      <Link href={analyzeHref({ symbol: s.symbol })} className="scan-sym">
                        {s.symbol}
                      </Link>
                    </td>
                    <td>
                      <div>{s.name || s.symbol}</div>
                      <div className="td-muted" style={{ fontSize: "var(--td-text-caption)" }}>
                        {s.product || s.industry || "—"}
                      </div>
                    </td>
                    <td className="tabular" style={{ color: `var(--${scoreRankClass(s.score ?? 0)})` }}>
                      {(s.score ?? 0).toFixed(2)}
                    </td>
                    <td>
                      <span className={`td-chip ${actionColorClass(s.play?.action)}`}>
                        {s.play?.action ?? "—"}
                      </span>
                    </td>
                    <td className="tabular">{pct(s.correlation_1y)}</td>
                    <td className="tabular">{pct(s.revenue_yoy)}</td>
                    <td className="tabular">{pct(s.free_cash_flow_yoy)}</td>
                    <td className="tabular">{capLabel(s.market_cap)}</td>
                    <td className="tabular" style={{ fontSize: "var(--td-text-caption)" }}>
                      {s.source}
                    </td>
                    <td className="tabular" style={{ fontSize: "var(--td-text-caption)", color: confColorVar(s.confidence) }}>
                      {s.confidence}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : result ? (
        <div className="td-panel p-3">
          <p className="td-muted">No suppliers discovered. Try a seed ticker or add OPENAI_API_KEY for web search.</p>
        </div>
      ) : null}
    </div>
  );
}

export default function SupplyChainDesk() {
  return (
    <Suspense
      fallback={
        <div className="td-page">
          <p className="td-muted">Loading desk…</p>
        </div>
      }
    >
      <SupplyChainDeskInner />
    </Suspense>
  );
}
