"use client";

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
import { QuickActionRail } from "@/components/command-center/QuickActionRail";
import { PageHeader } from "@/components/shell/PageHeader";
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
    <div className="td-page">
      <PageHeader
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
        <section className="td-command-intro" aria-labelledby="command-center-title">
          <div className="td-command-intro__copy">
            <span className="td-command-intro__status">
              <span className="td-status-dot" aria-hidden="true" />
              Analysis workspace ready
            </span>
            <h2 id="command-center-title">Start with the market, not a conclusion.</h2>
            <p>
              Enter a symbol to review the setup, its gates, the relevant levels, and an explicit risk-aware next action.
            </p>
          </div>
          <ol className="td-command-intro__protocol" aria-label="Analysis sequence">
            <li><span>01</span><div><strong>Read the market</strong><small>price, volume, and session context</small></div></li>
            <li><span>02</span><div><strong>Test the setup</strong><small>structure, signal, and safety gates</small></div></li>
            <li><span>03</span><div><strong>Size the decision</strong><small>levels, exposure, and next step</small></div></li>
          </ol>
        </section>
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
        <div className="td-mission-map td-panel">
          <PipelineFlow
            state={null}
            phase="idle"
            activeStage={-1}
          />
        </div>
      ) : null}

      {commandCenterIdle ? (
        <QuickActionRail />
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
