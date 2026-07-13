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
import { PageHeader } from "@/components/shell/PageHeader";
import type { AnalyzeResponse, ApiEnvelope, ModelMetaConfig } from "@/lib/types";

const STAGE_COUNT = 8;
const STAGE_MS = 280;

function AnalyzePageInner() {
  const searchParams = useSearchParams();
  const qSymbol = searchParams.get("symbol")?.toUpperCase() ?? "";
  const qModel = searchParams.get("model")?.trim() || "auto";

  const formRef = useRef<AnalyzeFormHandle>(null);
  const autoRanKey = useRef<string | null>(null);

  const [phase, setPhase] = useState<PipelinePhase>("idle");
  const [activeStage, setActiveStage] = useState(0);
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

  useEffect(() => {
    if (phase !== "running") return;
    setActiveStage(0);
    let stage = 0;
    const id = window.setInterval(() => {
      stage += 1;
      if (stage >= STAGE_COUNT) {
        window.clearInterval(id);
        return;
      }
      setActiveStage(stage);
    }, STAGE_MS);
    return () => window.clearInterval(id);
  }, [phase]);

  const runAnalyze = useCallback(async (values: AnalyzeFormValues) => {
    setSymbol(values.symbol);
    setActiveModel(values.model);
    setAccount(values.account);
    setError(null);
    setPhase("running");
    setActiveStage(0);
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
      await new Promise((r) => setTimeout(r, STAGE_MS));
      setResult(json.data);
      setActiveStage(STAGE_COUNT - 1);
      setPhase("done");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analyze failed");
      setPhase("error");
      setActiveStage(STAGE_COUNT - 1);
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

  return (
    <div className="td-page">
      <PageHeader
        title="Analyze"
        description="Operator ticket first: action, do next, entry/stop/size. Pipeline and gates are secondary."
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

      <AnalyzeForm
        ref={formRef}
        initialSymbol={symbol || qSymbol}
        initialModel={activeModel || qModel}
        disabled={running}
        onSubmit={runAnalyze}
        onModelChange={setActiveModel}
      />

      {error ? (
        <div className="td-alert td-alert--error" role="alert">
          {error}
        </div>
      ) : null}

      {/* Running: compact pipeline strip */}
      {phase === "running" ? (
        <div className="td-panel p-3">
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

      {/* Hero: verdict first */}
      <VerdictPanel
        symbol={symbol || state?.symbol}
        state={state}
        plan={plan}
        size={size}
        model={result?.model}
        selection={result?.model_selection}
        empty={phase === "idle" || (phase === "running" && !result)}
      />

      {phase === "done" && state ? (
        <ModelComputeTrace
          state={state}
          plan={plan}
          size={size}
          model={result?.model}
          selection={result?.model_selection}
        />
      ) : null}

      {phase === "done" && metaConfig ? (
        <div className="td-panel p-3">
          <ModelTuningView id={result?.model || activeModel} metaConfig={metaConfig} />
        </div>
      ) : null}

      {(symbol || state?.symbol || qSymbol) ? (
        <RankerPanel
          symbol={symbol || state?.symbol || qSymbol}
          account={account}
          activeModel={result?.model}
          onUseModel={onUseModel}
        />
      ) : null}

      {/* Levels visual — only when we have state */}
      {state || phase === "idle" ? <LevelsPanel state={state} /> : null}

      {/* Secondary research panels */}
      {phase === "done" || phase === "error" ? (
        <details className="td-details td-details--block" open={false}>
          <summary className="td-details__summary">
            Research: pipeline · live pulse · model ranks
          </summary>
          <div className="td-analyze-secondary mt-3 flex flex-col gap-3">
            {showPipeline ? (
              <div className="td-panel p-3">
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
