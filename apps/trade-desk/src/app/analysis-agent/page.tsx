"use client";

import { Suspense, useCallback, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  AnalyzeForm,
  type AnalyzeFormHandle,
  type AnalyzeFormValues,
} from "@/components/analyze/AnalyzeForm";
import { AnalysisReport } from "@/components/analysis-agent/AnalysisReport";
import { PageHeader } from "@/components/shell/PageHeader";
import type { AnalysisAgentResponse, AnalysisReport as AnalysisReportType, ApiEnvelope } from "@/lib/types";

function AnalysisAgentPageInner() {
  const searchParams = useSearchParams();
  const qSymbol = searchParams.get("symbol")?.toUpperCase() ?? "";
  const qModel = searchParams.get("model")?.trim() || "auto";

  const formRef = useRef<AnalyzeFormHandle>(null);
  const [phase, setPhase] = useState<"idle" | "running" | "done" | "error">("idle");
  const [symbol, setSymbol] = useState(qSymbol);
  const [activeModel, setActiveModel] = useState(qModel);
  const [report, setReport] = useState<AnalysisReportType | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runAgent = useCallback(async (values: AnalyzeFormValues) => {
    setSymbol(values.symbol);
    setActiveModel(values.model);
    setError(null);
    setReport(null);
    setPhase("running");

    try {
      const res = await fetch("/api/analysis-agent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: values.symbol,
          account: values.account,
          model: values.model === "auto" ? undefined : values.model,
        }),
      });
      const json = (await res.json()) as ApiEnvelope<AnalysisAgentResponse>;
      if (!res.ok || json.ok === false || !json.data?.report) {
        throw new Error(json.error ?? `Analysis Agent failed (${res.status})`);
      }
      setReport(json.data.report);
      setPhase("done");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analysis Agent failed");
      setPhase("error");
    }
  }, []);

  return (
    <div className="td-page">
      <PageHeader
        title="Analysis Agent"
        description="Facts → Decision → Suggestion. Reuses the live desk + model stack without touching the engines."
        meta={
          symbol ? (
            <span className="tabular" style={{ fontFamily: "var(--td-font-mono)" }}>
              {symbol}
              {activeModel ? (
                <span style={{ color: "var(--td-ink-400)" }}> · {activeModel}</span>
              ) : null}
            </span>
          ) : (
            <span>Enter a ticker to see the structured report.</span>
          )
        }
      />

      <AnalyzeForm
        ref={formRef}
        initialSymbol={symbol || qSymbol}
        initialModel={activeModel || qModel}
        disabled={phase === "running"}
        onSubmit={runAgent}
        onModelChange={setActiveModel}
      />

      {error ? (
        <div className="td-alert td-alert--error mt-4" role="alert">
          {error}
        </div>
      ) : null}

      {phase === "running" ? (
        <div className="td-panel mt-4" style={{ color: "var(--td-ink-400)" }}>
          <span className="td-live-pulse" aria-hidden />
          Running analysis agent…
        </div>
      ) : null}

      {phase === "done" && report ? (
        <div className="mt-4">
          <AnalysisReport symbol={symbol} model={activeModel} report={report} />
        </div>
      ) : null}
    </div>
  );
}

export default function AnalysisAgentPage() {
  return (
    <Suspense>
      <AnalysisAgentPageInner />
    </Suspense>
  );
}
