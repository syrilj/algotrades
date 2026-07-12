"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  AnalyzeForm,
  type AnalyzeFormValues,
} from "@/components/analyze/AnalyzeForm";
import { LevelsPanel } from "@/components/analyze/LevelsPanel";
import { TopModelsStrip } from "@/components/analyze/TopModelsStrip";
import { VerdictPanel } from "@/components/analyze/VerdictPanel";
import {
  PipelineFlow,
  type PipelinePhase,
} from "@/components/pipeline/PipelineFlow";
import type { AnalyzeResponse, ApiEnvelope } from "@/lib/types";

const STAGE_COUNT = 8;
const STAGE_MS = 420;

function AnalyzePageInner() {
  const searchParams = useSearchParams();
  const qSymbol = searchParams.get("symbol")?.toUpperCase() ?? "";

  const [phase, setPhase] = useState<PipelinePhase>("idle");
  const [activeStage, setActiveStage] = useState(0);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [symbol, setSymbol] = useState(qSymbol);
  const [forceAutoKey, setForceAutoKey] = useState(0);

  useEffect(() => {
    if (qSymbol) setSymbol(qSymbol);
  }, [qSymbol]);

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

  const onUseAuto = useCallback(() => {
    setForceAutoKey((k) => k + 1);
  }, []);

  const state = result?.state ?? null;
  const plan = result?.plan ?? null;
  const size = result?.size ?? null;

  return (
    <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-4 px-4 py-4">
      <AnalyzeForm
        key={forceAutoKey}
        initialSymbol={symbol || qSymbol}
        disabled={phase === "running"}
        onSubmit={runAnalyze}
      />

      {error ? (
        <div
          className="px-3 py-2 text-[12px]"
          role="alert"
          style={{
            border: "1px solid var(--td-action-avoid)",
            background: "#A3484818",
            color: "var(--td-action-avoid)",
            borderRadius: "var(--td-radius-sm)",
          }}
        >
          {error}
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(280px,0.9fr)]">
        <PipelineFlow
          state={state}
          plan={plan}
          size={size}
          model={result?.model}
          phase={phase}
          activeStage={activeStage}
        />
        <VerdictPanel
          symbol={symbol || state?.symbol}
          state={state}
          plan={plan}
          size={size}
          model={result?.model}
          selection={result?.model_selection}
          empty={phase === "idle" || (phase === "running" && !result)}
        />
      </div>

      <LevelsPanel state={state} />

      {(symbol || state?.symbol) && phase === "done" ? (
        <TopModelsStrip
          symbol={symbol || state?.symbol || ""}
          ranks={result?.model_ranks_for_symbol}
          onUseAuto={onUseAuto}
        />
      ) : null}
    </div>
  );
}

export default function AnalyzePage() {
  return (
    <Suspense
      fallback={
        <div className="px-4 py-4 text-[12px]" style={{ color: "var(--td-ink-400)" }}>
          Loading desk…
        </div>
      }
    >
      <AnalyzePageInner />
    </Suspense>
  );
}
