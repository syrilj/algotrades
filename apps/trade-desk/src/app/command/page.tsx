"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  AnalyzeForm,
  type AnalyzeFormHandle,
  type AnalyzeFormValues,
} from "@/components/analyze/AnalyzeForm";
import { ModelComputeTrace } from "@/components/analyze/ModelComputeTrace";
import { LevelsPanel } from "@/components/analyze/LevelsPanel";
import { RankerPanel } from "@/components/analyze/RankerPanel";
import { VerdictPanel } from "@/components/analyze/VerdictPanel";
import { LiveSignalPanel } from "@/components/LiveSignalPanel";
import { ModelTuningView } from "@/components/models/ModelTuningView";
import {
  PipelineFlow,
  type PipelinePhase,
} from "@/components/pipeline/PipelineFlow";
import { RiskAssessmentPanel } from "@/components/risk/RiskAssessmentPanel";
import { PageHeader } from "@/components/shell/PageHeader";
import { QuickActionRail } from "@/components/command-center/QuickActionRail";
import type { AnalyzeResponse, ApiEnvelope, ModelMetaConfig } from "@/lib/types";

function AnalyzePageInner() {
  const searchParams = useSearchParams();
  const qSymbol = searchParams.get("symbol")?.toUpperCase() ?? "";
  const qModel = searchParams.get("model")?.trim() || "auto";

  const formRef = useRef<AnalyzeFormHandle>(null);
  const autoRanKey = useRef<string | null>(null);

  const [phase, setPhase] = useState<PipelinePhase>("idle");
  const [activeStage, setActiveStage] = useState(-1);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [symbol, setSymbol] = useState(qSymbol);
  const [activeModel, setActiveModel] = useState(qModel);
  const [account, setAccount] = useState(100_000);
  const [metaConfig, setMetaConfig] = useState<ModelMetaConfig | null>(null);

  useEffect(() => {
    if (qSymbol) setSymbol(qSymbol);
  }, [qSymbol]);

  useEffect(() => {
    if (qModel) setActiveModel(qModel);
  }, [qModel]);

  useEffect(() => {
    const modelId = result?.model || (activeModel !== "auto" ? activeModel : "");
    if (!modelId) {
      setMetaConfig(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/models?id=${encodeURIComponent(modelId)}`);
        const json = (await res.json()) as ApiEnvelope<{
          meta_config: ModelMetaConfig | null;
        }>;
        if (!cancelled && json.ok && json.data) {
          setMetaConfig(json.data.meta_config ?? null);
        }
      } catch {
        if (!cancelled) setMetaConfig(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [activeModel, result?.model]);

  const runAnalyze = useCallback(async (values: AnalyzeFormValues) => {
    setSymbol(values.symbol);
    setActiveModel(values.model);
    setAccount(values.account);
    setError(null);
    setPhase("running");
    setActiveStage(-1);
    setResult(null);

    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: values.symbol,
          account: values.account,
          risk_pct: values.riskPct,
          model: values.model === "auto" ? undefined : values.model,
          period: values.period,
          interval: values.interval,
          auto: values.model === "auto",
        }),
      });
      const json = (await res.json()) as ApiEnvelope<AnalyzeResponse>;
      if (!res.ok || json.ok === false || !json.data) {
        throw new Error(json.error ?? `Analyze failed (${res.status})`);
      }
      setResult(json.data);
      setActiveStage(7);
      setPhase("done");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analyze failed");
      setPhase("error");
      setActiveStage(7);
    }
  }, []);

  // Deep-link: clicking a stock / model route lands here and auto-runs once.
  useEffect(() => {
    if (!qSymbol) return;
    const key = `${qSymbol}|${qModel}`;
    if (autoRanKey.current === key) return;
    autoRanKey.current = key;
    const t = window.setTimeout(() => {
      formRef.current?.submitWith({
        symbol: qSymbol,
        model: qModel || "auto",
      });
    }, 60);
    return () => window.clearTimeout(t);
  }, [qSymbol, qModel]);

  const onUseModel = useCallback((model: string) => {
    formRef.current?.setModel(model);
    formRef.current?.submitWith({
      symbol: symbol || qSymbol,
      model,
    });
  }, [symbol, qSymbol]);

  const state = result?.state ?? null;
  const plan = result?.plan ?? null;
  const size = result?.size ?? null;
  const running = phase === "running";
  const showPipeline = phase === "running" || phase === "done" || phase === "error";
  const commandCenterIdle = phase === "idle" && !symbol && !qSymbol;

  return (
    <div className="td-page td-command-theme">
      <PageHeader
        eyebrow="Desk"
        title="Command"
        description="A traceable route from market data to a risk-aware operator decision."
        meta={
          symbol ? (
            <span className="tabular" style={{ fontFamily: "var(--td-font-mono)" }}>
              {symbol}
              {activeModel ? (
                <span style={{ color: "var(--td-ink-400)" }}> · {activeModel}</span>
              ) : null}
              {phase === "done" && plan?.action ? (
                <span style={{ color: "var(--td-ink-400)" }}> · {plan.action}</span>
              ) : null}
            </span>
          ) : (
            <span>Enter a ticker or open a name from Watch / Picks / Live</span>
          )
        }
      />

      {commandCenterIdle ? (
        <div className="flex flex-col gap-6 mb-6">
          <QuickActionRail />

          {/* Typographic Serif Header */}
          <header className="td-landing-hero">
            <h1 className="td-landing-title">Start with the market, not a conclusion.</h1>
            <p className="td-landing-subtitle">
              Enter a symbol below or click a winner bag asset to trace its volume profile, HTF trend bias, risk parameters, and meta-model execution.{" "}
              <Link href="/" className="td-landing-welcome-link">
                View product tour →
              </Link>
            </p>
          </header>

          {/* Active Winner Bag Quick-Links */}
          <section className="td-winner-bag-section">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-2 border-b border-[var(--td-hairline)] pb-3">
              <div>
                <h2 className="text-sm font-semibold text-[var(--td-ink)] flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-[var(--td-brand)] animate-pulse" />
                  Active Winner Bag Assets
                </h2>
                <p className="text-[12px] text-[var(--td-muted)] mt-1">
                  Elite names from backtest campaigns. Select to run auto-routed live analysis.
                </p>
              </div>
              <span className="text-[10px] font-mono text-[var(--td-muted)] bg-[var(--td-surface-elevated)] px-2.5 py-1 rounded">
                source: local adjusted 1H
              </span>
            </div>

            <div className="td-winner-bag-grid">
              {[
                { code: "TSLA", name: "Tesla Inc." },
                { code: "MU", name: "Micron Tech" },
                { code: "SPY", name: "S&P 500 ETF" },
                { code: "IONQ", name: "IonQ Inc." },
                { code: "APLD", name: "Applied Digital" },
                { code: "XLP", name: "Consumer Staples" },
                { code: "QQQ", name: "Nasdaq 100 ETF" },
              ].map((item) => (
                <button
                  key={item.code}
                  type="button"
                  onClick={() => {
                    formRef.current?.submitWith({
                      symbol: item.code,
                      model: "auto",
                    });
                  }}
                  className="td-winner-bag-card text-left align-middle"
                >
                  <strong>{item.code}</strong>
                  <span>{item.name}</span>
                </button>
              ))}
            </div>
          </section>

          {/* Model Processing Protocol */}
          <section className="td-protocol-map">
            <h2 className="text-sm font-semibold text-[var(--td-ink)]">Model Execution Protocol</h2>
            <p className="text-[12px] text-[var(--td-muted)]">
              Causal multi-stage gate filters running live on request.
            </p>
            <div className="td-protocol-flow">
              <span className="td-protocol-node td-protocol-node--active">01 OHLCV</span>
              <span className="td-protocol-arrow">→</span>
              <span className="td-protocol-node td-protocol-node--active">02 Vol Profile (VAL/VAH/POC)</span>
              <span className="td-protocol-arrow">→</span>
              <span className="td-protocol-node td-protocol-node--active">03 HTF HA Bias</span>
              <span className="td-protocol-arrow">→</span>
              <span className="td-protocol-node td-protocol-node--active">04 Rule Long</span>
              <span className="td-protocol-arrow">→</span>
              <span className="td-protocol-node td-protocol-node--active">05 Filters</span>
              <span className="td-protocol-arrow">→</span>
              <span className="td-protocol-node td-protocol-node--active">06 Kelly Sizing</span>
              <span className="td-protocol-arrow">→</span>
              <span className="td-protocol-node td-protocol-node--active">07 Meta-XGB</span>
              <span className="td-protocol-arrow">→</span>
              <span className="td-protocol-node td-protocol-node--active">08 Action & Sizing</span>
            </div>
          </section>
        </div>
      ) : null}

      <AnalyzeForm
        ref={formRef}
        initialSymbol={symbol || qSymbol}
        initialModel={activeModel || qModel}
        disabled={running}
        onSubmit={runAnalyze}
        onModelChange={setActiveModel}
      />

      {commandCenterIdle ? (
        <section className="flex flex-col gap-3 mt-6">
          <div className="border-b border-[var(--td-hairline)] pb-3">
            <h2 className="text-sm font-semibold text-[var(--td-ink)]">System Champions & Backtest Performance</h2>
            <p className="text-[12px] text-[var(--td-muted)] mt-1">
              Audited benchmark model stats reconciled on local historical database (1H interval).
            </p>
          </div>

          <div className="td-dashboard-grid">
            {/* Champion Card */}
            <article className="td-metric-card td-metric-card--winner">
              <div className="flex items-start justify-between">
                <div>
                  <span className="text-[10px] font-mono text-[var(--td-brand)] uppercase tracking-wider font-semibold">
                    Live Combined Champion
                  </span>
                  <h3 className="text-base font-semibold text-[var(--td-ink)] mt-1">v72_dual_sleeve</h3>
                </div>
                <span className="text-[10px] text-[var(--td-body)] bg-[var(--td-surface-elevated)] px-2 py-0.5 rounded font-mono">
                  Sniper + Core
                </span>
              </div>
              
              <p className="text-[12px] text-[var(--td-body)] leading-relaxed">
                Hierarchical consensus sleeve. Stacks sniper triggers with a scaled core model. Selected for live routing.
              </p>

              <div className="td-metric-grid border-t border-[var(--td-hairline)] pt-3">
                <div className="td-metric-item">
                  <span className="td-metric-value text-[var(--td-brand)]">+513.1%</span>
                  <span className="td-metric-label">Full Return</span>
                </div>
                <div className="td-metric-item">
                  <span className="td-metric-value">-19.4%</span>
                  <span className="td-metric-label">Max Drawdown</span>
                </div>
                <div className="td-metric-item">
                  <span className="td-metric-value">3.08</span>
                  <span className="td-metric-label">Sharpe Ratio</span>
                </div>
                <div className="td-metric-item">
                  <span className="td-metric-value">72.1%</span>
                  <span className="td-metric-label">Win Rate</span>
                </div>
              </div>

              <div className="text-[11px] text-[var(--td-muted)] bg-[var(--td-surface-soft)] p-2 rounded flex justify-between font-mono">
                <span>Holdout (OOS): +81.6%</span>
                <span>Sharpe: 2.20 (n=84)</span>
              </div>
            </article>

            {/* Best Single Card */}
            <article className="td-metric-card">
              <div className="flex items-start justify-between">
                <div>
                  <span className="text-[10px] font-mono text-[var(--td-muted)] uppercase tracking-wider font-semibold">
                    Best Pure Single Model
                  </span>
                  <h3 className="text-base font-semibold text-[var(--td-ink)] mt-1">v39d_confluence</h3>
                </div>
                <span className="text-[10px] text-[var(--td-body)] bg-[var(--td-surface-elevated)] px-2 py-0.5 rounded font-mono">
                  Confluence
                </span>
              </div>

              <p className="text-[12px] text-[var(--td-body)] leading-relaxed">
                Consensus engine using dual RSI thresholds and MACD histogram momentum filters. Tighter baseline drawdown.
              </p>

              <div className="td-metric-grid border-t border-[var(--td-hairline)] pt-3">
                <div className="td-metric-item">
                  <span className="td-metric-value">+357.5%</span>
                  <span className="td-metric-label">Full Return</span>
                </div>
                <div className="td-metric-item">
                  <span className="td-metric-value">-13.4%</span>
                  <span className="td-metric-label">Max Drawdown</span>
                </div>
                <div className="td-metric-item">
                  <span className="td-metric-value">2.82</span>
                  <span className="td-metric-label">Sharpe Ratio</span>
                </div>
                <div className="td-metric-item">
                  <span className="td-metric-value">67.0%</span>
                  <span className="td-metric-label">Win Rate</span>
                </div>
              </div>

              <div className="text-[11px] text-[var(--td-muted)] bg-[var(--td-surface-soft)] p-2 rounded flex justify-between font-mono">
                <span>Trades (n): 135</span>
                <span>Source: Local adjusted</span>
              </div>
            </article>

            {/* High WR Sniper Card */}
            <article className="td-metric-card">
              <div className="flex items-start justify-between">
                <div>
                  <span className="text-[10px] font-mono text-[var(--td-muted)] uppercase tracking-wider font-semibold">
                    High Win Rate Sleeve
                  </span>
                  <h3 className="text-base font-semibold text-[var(--td-ink)] mt-1">v71_live_confidence</h3>
                </div>
                <span className="text-[10px] text-[var(--td-body)] bg-[var(--td-surface-elevated)] px-2 py-0.5 rounded font-mono">
                  Sniper
                </span>
              </div>

              <p className="text-[12px] text-[var(--td-body)] leading-relaxed">
                Gated mean-reversion using SMA(250) macro trend filters with dynamic confidence-based size-up allocations.
              </p>

              <div className="td-metric-grid border-t border-[var(--td-hairline)] pt-3">
                <div className="td-metric-item">
                  <span className="td-metric-value">+114.0%</span>
                  <span className="td-metric-label">Full Return</span>
                </div>
                <div className="td-metric-item">
                  <span className="td-metric-value">-19.5%</span>
                  <span className="td-metric-label">Max Drawdown</span>
                </div>
                <div className="td-metric-item">
                  <span className="td-metric-value">1.72</span>
                  <span className="td-metric-label">Sharpe Ratio</span>
                </div>
                <div className="td-metric-item">
                  <span className="td-metric-value text-[var(--td-brand)]">86.0%</span>
                  <span className="td-metric-label">Win Rate</span>
                </div>
              </div>

              <div className="text-[11px] text-[var(--td-muted)] bg-[var(--td-surface-soft)] p-2 rounded flex justify-between font-mono">
                <span>Holdout (OOS): +30.9%</span>
                <span>OOS Win Rate: 76.9%</span>
              </div>
            </article>
          </div>
        </section>
      ) : null}

      {error ? (
        <div className="td-alert td-alert--error" role="alert">
          {error}
        </div>
      ) : null}

      {/* The execution path stays visible; it is the explanation, not a hidden research detail. */}
      {showPipeline && !commandCenterIdle ? (
        <div className="td-mission-map td-panel">
          <PipelineFlow
            state={state}
            plan={plan}
            size={size}
            model={result?.model}
            phase={phase}
            activeStage={activeStage}
          />
        </div>
      ) : null}

      {/* Hero: verdict + levels + trace / ranker + tuning side-by-side */}
      {!commandCenterIdle ? (
        <div className="td-analyze-grid">
          <div className="td-analyze-main flex flex-col gap-3">
            <VerdictPanel
              symbol={symbol || state?.symbol}
              state={state}
              plan={plan}
              size={size}
              model={result?.model}
              selection={result?.model_selection}
              empty={phase === "idle" || (phase === "running" && !result)}
            />

            {state || (phase === "idle" && !commandCenterIdle) ? (
              <LevelsPanel state={state} />
            ) : null}

            {phase === "done" && state ? (
              <ModelComputeTrace
                state={state}
                plan={plan}
                size={size}
                model={result?.model}
                selection={result?.model_selection}
              />
            ) : null}
          </div>

          <div className="td-analyze-side">
            {(symbol || state?.symbol || qSymbol) ? (
              <RankerPanel
                symbol={symbol || state?.symbol || qSymbol}
                account={account}
                activeModel={result?.model}
                onUseModel={onUseModel}
              />
            ) : null}

            {phase === "done" && metaConfig ? (
              <div className="td-panel p-3">
                <ModelTuningView id={result?.model || activeModel} metaConfig={metaConfig} />
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {/* Secondary research panels */}
      {phase === "done" || phase === "error" ? (
        <details className="td-details td-details--block" open={false}>
          <summary className="td-details__summary">
            Research: pipeline · live pulse · model ranks
          </summary>
          <div className="td-analyze-secondary mt-3 flex flex-col gap-3">
            {(symbol || state?.symbol) && phase === "done" ? (
              <LiveSignalPanel symbol={symbol || state?.symbol || ""} />
            ) : null}
            {(symbol || state?.symbol) && phase === "done" ? (
              <RiskAssessmentPanel
                symbol={symbol || state?.symbol || ""}
                account={account}
              />
            ) : null}
          </div>
        </details>
      ) : null}

      {phase === "idle" && (symbol || qSymbol) ? (
        <LiveSignalPanel symbol={symbol || qSymbol} />
      ) : null}
    </div>
  );
}

export default function AnalyzePage() {
  return (
    <Suspense
      fallback={
        <div className="td-page">
          <p className="td-muted">Loading desk…</p>
        </div>
      }
    >
      <AnalyzePageInner />
    </Suspense>
  );
}
