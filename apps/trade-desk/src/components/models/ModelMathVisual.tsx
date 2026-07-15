"use client";

import React, { useState, useMemo } from "react";
import {
  Sliders,
  ChevronRight,
  Workflow,
  Binary,
  AlertCircle,
  Info,
  Scale
} from "lucide-react";
import type { ModelMetaConfig } from "@/lib/types";

type ModelMathVisualProps = {
  modelId: string;
  metaConfig?: ModelMetaConfig | null;
  className?: string;
};

type ModelCategory = "confluence" | "arete" | "ensemble" | "mean_reversion" | "microstructure";

export function ModelMathVisual({ modelId, metaConfig, className = "" }: ModelMathVisualProps) {
  const [activeTab, setActiveTab] = useState<"architecture" | "math" | "simulator">("architecture");
  const [selectedNode, setSelectedNode] = useState<string | null>(null);

  // Classify model ID into a category
  const category = useMemo<ModelCategory>(() => {
    const id = modelId.toLowerCase();
    if (id.includes("v60") || id.includes("v61") || id.includes("microstructure") || id.includes("institutional_flow") || id.includes("absorption")) {
      return "microstructure";
    }
    if (id.includes("v50") || id.includes("v45") || id.includes("ultimate_rsi") || id.includes("high_win_rate") || id.includes("v70")) {
      return "mean_reversion";
    }
    if (id.includes("v41") || id.includes("ensemble")) {
      return "ensemble";
    }
    if (id.includes("v40") || id.includes("arete")) {
      return "arete";
    }
    return "confluence";
  }, [modelId]);

  // Read config defaults
  const configParams = useMemo(() => {
    const p = metaConfig?.params || {};
    return {
      threshold: typeof metaConfig?.threshold === "number" ? metaConfig.threshold : 0.55,
      rsi_len: typeof p.rsi_len === "number" ? p.rsi_len : 14,
      sma_len: typeof p.sma_len === "number" ? p.sma_len : 250,
      vpin_len: typeof p.vpin_len === "number" ? p.vpin_len : 50,
      lookback: typeof p.perf_lookback === "number" ? p.perf_lookback : 60,
      temperature: typeof p.perf_temperature === "number" ? p.perf_temperature : 0.5,
      signal_scale: typeof p.signal_scale === "number" ? p.signal_scale : 0.225,
      fib_threshold: typeof p.fib_threshold === "number" ? p.fib_threshold : 0.2,
      ...p
    };
  }, [metaConfig]);

  // Interactive Simulator States
  // 1. Confluence States
  const [confVpa, setConfVpa] = useState(0.8); // VPA score
  const [confXgb, setConfXgb] = useState(0.58); // XGB score
  const [confInsideVa, setConfInsideVa] = useState(true); // Proximity to VAL/POC
  const [confStreak, setConfStreak] = useState(1); // Win streak

  // 2. Arete States
  const [areteFibDist, setAreteFibDist] = useState(0.12); // Distance to closest Fib level
  const [areteMaTrend, setAreteMaTrend] = useState(true); // Close > EMA(200) & EMA(50) > EMA(200)
  const [areteSoxRegime, setAreteSoxRegime] = useState(true); // Semiconductor bias (Risk On)

  // 3. Ensemble States
  const [ensSharpeA, setEnsSharpeA] = useState(2.82); // Sharpe of v39d
  const [ensSharpeB, setEnsSharpeB] = useState(2.70); // Sharpe of v39b
  const [ensTemp, setEnsTemp] = useState(0.5); // Temp config

  // 4. Mean Reversion States
  const [mrRsi7, setMrRsi7] = useState(24);
  const [mrRsi14, setMrRsi14] = useState(28);
  const [mrRsi28, setMrRsi28] = useState(35);
  const [mrAboveSma, setMrAboveSma] = useState(true);

  // 5. Microstructure States
  const [micVpin, setMicVpin] = useState(0.72);
  const [micOfi, setMicOfi] = useState(1.4);
  const [micAbsorb, setMicAbsorb] = useState(2.5);
  const [micXgb, setMicXgb] = useState(0.62);

  // --- Real-time math engine calculators for the simulator ---

  // Confluence Sizing & Verdict
  const confOutputs = useMemo(() => {
    const passedXgb = confXgb >= configParams.threshold;
    const passedVa = confInsideVa;
    const passedVpa = confVpa > 0;
    const verdict = passedXgb && passedVa && passedVpa ? "BUY" : "STAND ASIDE";
    
    // Size multiplier = base size * vpa_multiplier * streak_multiplier
    const vpaMult = Math.min(1.5, Math.max(0.5, 0.5 + confVpa));
    const streakMult = confStreak >= 0 ? 1.0 + confStreak * 0.1 : 1.0 / (1.0 - confStreak);
    const rawSize = verdict === "BUY" ? 0.15 * vpaMult * streakMult : 0.0;
    
    return { verdict, vpaMult, streakMult, size: Math.min(0.5, rawSize) };
  }, [confXgb, confInsideVa, confVpa, confStreak, configParams.threshold]);

  // Arete Overlays
  const areteOutputs = useMemo(() => {
    const fibPass = areteFibDist <= configParams.fib_threshold;
    const maPass = areteMaTrend;
    const soxPass = areteSoxRegime;
    const verdict = fibPass && maPass && soxPass ? "APPROVED" : "BLOCKED";
    return { verdict, fibPass, maPass, soxPass };
  }, [areteFibDist, areteMaTrend, areteSoxRegime, configParams.fib_threshold]);

  // Ensemble Weights (Softmax)
  const ensembleOutputs = useMemo(() => {
    const expA = Math.exp(ensSharpeA / ensTemp);
    const expB = Math.exp(ensSharpeB / ensTemp);
    const sum = expA + expB;
    const wA = expA / sum;
    const wB = expB / sum;
    return { wA, wB };
  }, [ensSharpeA, ensSharpeB, ensTemp]);

  // Mean Reversion
  const mrOutputs = useMemo(() => {
    // Ultimate RSI = (4*RSI7 + 2*RSI14 + 1*RSI28) / 7
    const ultRsi = (4 * mrRsi7 + 2 * mrRsi14 + mrRsi28) / 7;
    const isOversold = ultRsi < 30;
    const isTrendPass = mrAboveSma;
    const verdict = isOversold && isTrendPass ? "BUY (Mean Reversion)" : "STAND ASIDE (No Setup)";
    const size = verdict.startsWith("BUY") ? configParams.signal_scale : 0.0;
    return { ultRsi, isOversold, verdict, size };
  }, [mrRsi7, mrRsi14, mrRsi28, mrAboveSma, configParams.signal_scale]);

  // Microstructure
  const micOutputs = useMemo(() => {
    const isToxic = micVpin > 0.65;
    const isAbsorbing = micAbsorb > 2.0;
    const hasBuyFlow = micOfi > 0.8;
    const xgbPass = micXgb >= 0.58;
    
    // Sizing scales down with toxicity, scales up with absorbing buy flow
    let verdict = "STAND ASIDE";
    let size = 0.0;

    if (xgbPass && !isToxic && hasBuyFlow) {
      verdict = "HIGH CONVICTION BUY";
      size = configParams.signal_scale * (1.2 + (micAbsorb - 2.0) * 0.1);
    } else if (xgbPass && hasBuyFlow) {
      verdict = "MODERATE BUY (Toxic Flow)";
      size = configParams.signal_scale * 0.6;
    } else if (xgbPass) {
      verdict = "WEAK BUY (No OFI consensus)";
      size = configParams.signal_scale * 0.3;
    }

    return { verdict, isToxic, isAbsorbing, hasBuyFlow, size: Math.max(0, size) };
  }, [micVpin, micOfi, micAbsorb, micXgb, configParams.signal_scale]);

  // Render Strategy Title and Header Badge
  const metaHeader = useMemo(() => {
    switch (category) {
      case "microstructure":
        return {
          title: "Microstructure & Flow Toxicity Engine",
          desc: "OHLCV-safe proxies for Order Flow Imbalance (OFI), VPIN adverse selection, volume-price absorption ratios, and ML meta classification.",
          badgeColor: "text-amber-400 bg-amber-400/10 border-amber-400/20"
        };
      case "mean_reversion":
        return {
          title: "Ultimate RSI Mean-Reversion",
          desc: "Deep oversold reversion signals mapped over multiple lookup windows, gated with long-term moving average trend bias filters.",
          badgeColor: "text-teal-400 bg-teal-400/10 border-teal-400/20"
        };
      case "ensemble":
        return {
          title: "Performance-Weighted Multi-Teacher Ensemble",
          desc: "Autonomously weights multiple underlying model outputs by mapping recent lookback performance metric dynamics through a Softmax scale.",
          badgeColor: "text-purple-400 bg-purple-400/10 border-purple-400/20"
        };
      case "arete":
        return {
          title: "Arete Multi-Gate Safety Overlay",
          desc: "Filters and gates high-frequency entries using strict mathematical constraints on Fibonacci levels, sector momentum, and long-term trend lines.",
          badgeColor: "text-sky-400 bg-sky-400/10 border-sky-400/20"
        };
      default:
        return {
          title: "Volume Node & HA Trend Confluence",
          desc: "Matches structural inventory levels (Value Area nodes) with Heikin Ashi trend indicators, volume spread analysis, and XGBoost filters.",
          badgeColor: "text-emerald-400 bg-emerald-400/10 border-emerald-400/20"
        };
    }
  }, [category]);

  return (
    <div
      className={`border rounded-sm overflow-hidden flex flex-col ${className}`}
      style={{
        background: "var(--td-ink-900, #0c0c0c)",
        borderColor: "var(--td-ink-700, #2a2a2a)"
      }}
    >
      {/* Top Header Card */}
      <div className="p-4 border-b border-hairline flex flex-col md:flex-row md:items-center justify-between gap-3 bg-gradient-to-r from-surface-soft via-transparent to-transparent">
        <div>
          <div className="flex items-center gap-2">
            <span className={`text-[10px] font-bold px-2 py-0.5 border rounded-full uppercase tracking-wider ${metaHeader.badgeColor}`}>
              {category.replace("_", " ")}
            </span>
            <span className="text-[12px] text-muted font-mono">{modelId} Architecture</span>
          </div>
          <h3 className="text-[18px] font-medium text-body-strong mt-1 font-display">
            {metaHeader.title}
          </h3>
          <p className="text-[13px] text-muted max-w-3xl mt-1 leading-snug">
            {metaHeader.desc}
          </p>
        </div>
        
        {/* Navigation Tabs */}
        <div className="flex bg-surface rounded-sm p-0.5 border border-hairline shrink-0">
          {(
            [
              ["architecture", "Architecture", Workflow],
              ["math", "Math & Logic", Binary],
              ["simulator", "Live Simulator", Sliders]
            ] as const
          ).map(([tabId, label, Icon]) => (
            <button
              key={tabId}
              onClick={() => setActiveTab(tabId)}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium transition-all rounded-sm ${
                activeTab === tabId
                  ? "bg-brand text-white shadow-sm"
                  : "text-muted hover:text-body-strong"
              }`}
            >
              <Icon size={13} />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Main Content Body */}
      <div className="p-4 flex-1">
        {/* TAB 1: ARCHITECTURE BLOCK FLOW */}
        {activeTab === "architecture" && (
          <div className="flex flex-col lg:flex-row gap-6 min-h-[350px]">
            {/* Left Hand: Visual Node Pipeline */}
            <div className="flex-1 flex flex-col justify-center border border-hairline bg-surface p-4 rounded-sm">
              <h4 className="text-[12px] font-mono uppercase text-muted mb-3 flex items-center gap-1">
                <Workflow size={13} className="text-brand" /> Interactive Pipeline Blocks (Click nodes to inspect theory)
              </h4>
              
              <div className="flex flex-col gap-3 py-2">
                {category === "confluence" && (
                  <>
                    <div className="grid grid-cols-3 gap-2">
                      <button
                        onClick={() => setSelectedNode("ohlcv_in")}
                        className={`p-3 border text-left rounded-sm transition-all ${
                          selectedNode === "ohlcv_in" ? "border-emerald-500 bg-emerald-950/20 shadow-md" : "border-hairline hover:border-muted"
                        }`}
                      >
                        <div className="text-[10px] text-muted font-mono">01. INGEST</div>
                        <div className="text-[13px] font-medium text-body-strong">OHLCV Feed</div>
                        <span className="text-[10px] text-muted">Bar high, low, close & volume.</span>
                      </button>

                      <button
                        onClick={() => setSelectedNode("va_nodes")}
                        className={`p-3 border text-left rounded-sm transition-all ${
                          selectedNode === "va_nodes" ? "border-emerald-500 bg-emerald-950/20 shadow-md" : "border-hairline hover:border-muted"
                        }`}
                      >
                        <div className="text-[10px] text-muted font-mono">02. STRUCTURE</div>
                        <div className="text-[13px] font-medium text-body-strong">Value Area Nodes</div>
                        <span className="text-[10px] text-muted">POC, VAL, VAH ranges.</span>
                      </button>

                      <button
                        onClick={() => setSelectedNode("ha_trend")}
                        className={`p-3 border text-left rounded-sm transition-all ${
                          selectedNode === "ha_trend" ? "border-emerald-500 bg-emerald-950/20 shadow-md" : "border-hairline hover:border-muted"
                        }`}
                      >
                        <div className="text-[10px] text-muted font-mono">03. MOMENTUM</div>
                        <div className="text-[13px] font-medium text-body-strong">Heikin Ashi Trend</div>
                        <span className="text-[10px] text-muted">HTF MACD direction bias.</span>
                      </button>
                    </div>

                    <div className="flex justify-center my-1"><ChevronRight size={18} className="text-muted rotate-90" /></div>

                    <div className="grid grid-cols-2 gap-2">
                      <button
                        onClick={() => setSelectedNode("vpa_score")}
                        className={`p-3 border text-left rounded-sm transition-all ${
                          selectedNode === "vpa_score" ? "border-emerald-500 bg-emerald-950/20 shadow-md" : "border-hairline hover:border-muted"
                        }`}
                      >
                        <div className="text-[10px] text-muted font-mono">04. CORROBORATION</div>
                        <div className="text-[13px] font-medium text-body-strong">VPA Agreement</div>
                        <span className="text-[10px] text-muted">Coulling volume-spread consensus.</span>
                      </button>

                      <button
                        onClick={() => setSelectedNode("xgb_gate")}
                        className={`p-3 border text-left rounded-sm transition-all ${
                          selectedNode === "xgb_gate" ? "border-emerald-500 bg-emerald-950/20 shadow-md" : "border-hairline hover:border-muted"
                        }`}
                      >
                        <div className="text-[10px] text-muted font-mono">05. CLASSIFIER</div>
                        <div className="text-[13px] font-medium text-body-strong">XGBoost Prob Gate</div>
                        <span className="text-[10px] text-muted">Probability threshold &ge; {configParams.threshold}.</span>
                      </button>
                    </div>

                    <div className="flex justify-center my-1"><ChevronRight size={18} className="text-muted rotate-90" /></div>

                    <button
                      onClick={() => setSelectedNode("confl_sizing")}
                      className={`p-3 border text-left rounded-sm transition-all ${
                        selectedNode === "confl_sizing" ? "border-emerald-500 bg-emerald-950/20 shadow-md" : "border-hairline hover:border-muted"
                      }`}
                    >
                      <div className="text-[10px] text-muted font-mono">06. SIZING & ENTRY</div>
                      <div className="text-[13px] font-medium text-body-strong">Adaptive Trade Allocation</div>
                      <span className="text-[10px] text-muted">Sizing scaled dynamically by Win/Loss streaks and VPA score velocity.</span>
                    </button>
                  </>
                )}

                {category === "arete" && (
                  <>
                    <button
                      onClick={() => setSelectedNode("arete_input")}
                      className={`p-3 border text-left rounded-sm transition-all ${
                        selectedNode === "arete_input" ? "border-sky-500 bg-sky-950/20 shadow-md" : "border-hairline hover:border-muted"
                      }`}
                    >
                      <div className="text-[10px] text-muted font-mono">SIGNAL STAGE</div>
                      <div className="text-[13px] font-medium text-body-strong">v39b Entry Signal Triggered</div>
                      <span className="text-[10px] text-muted">A long signal is proposed by the primary model.</span>
                    </button>

                    <div className="flex justify-center my-1"><ChevronRight size={18} className="text-muted rotate-90" /></div>

                    <div className="grid grid-cols-3 gap-2">
                      <button
                        onClick={() => setSelectedNode("arete_fib")}
                        className={`p-3 border text-left rounded-sm transition-all ${
                          selectedNode === "arete_fib" ? "border-sky-500 bg-sky-950/20 shadow-md" : "border-hairline hover:border-muted"
                        }`}
                      >
                        <div className="text-[10px] text-muted font-mono">GATE 01</div>
                        <div className="text-[13px] font-medium text-body-strong">Fibonacci Level</div>
                        <span className="text-[10px] text-muted">Check distance &le; {configParams.fib_threshold} ATR of Retracements.</span>
                      </button>

                      <button
                        onClick={() => setSelectedNode("arete_ma")}
                        className={`p-3 border text-left rounded-sm transition-all ${
                          selectedNode === "arete_ma" ? "border-sky-500 bg-sky-950/20 shadow-md" : "border-hairline hover:border-muted"
                        }`}
                      >
                        <div className="text-[10px] text-muted font-mono">GATE 02</div>
                        <div className="text-[13px] font-medium text-body-strong">Trend Alignment</div>
                        <span className="text-[10px] text-muted">Verify Close &gt; EMA(200) and EMA(50) &gt; EMA(200).</span>
                      </button>

                      <button
                        onClick={() => setSelectedNode("arete_sox")}
                        className={`p-3 border text-left rounded-sm transition-all ${
                          selectedNode === "arete_sox" ? "border-sky-500 bg-sky-950/20 shadow-md" : "border-hairline hover:border-muted"
                        }`}
                      >
                        <div className="text-[10px] text-muted font-mono">GATE 03</div>
                        <div className="text-[13px] font-medium text-body-strong">Index Regime</div>
                        <span className="text-[10px] text-muted">Validate Sector/Macro index (e.g. SOX) has bullish momentum.</span>
                      </button>
                    </div>

                    <div className="flex justify-center my-1"><ChevronRight size={18} className="text-muted rotate-90" /></div>

                    <button
                      onClick={() => setSelectedNode("arete_execution")}
                      className={`p-3 border text-left rounded-sm transition-all ${
                        selectedNode === "arete_execution" ? "border-sky-500 bg-sky-950/20 shadow-md" : "border-hairline hover:border-muted"
                      }`}
                    >
                      <div className="text-[10px] text-muted font-mono">EXECUTION</div>
                      <div className="text-[13px] font-medium text-body-strong">Execute Order or Stand Aside</div>
                      <span className="text-[10px] text-muted">All gates must pass. If any gate fails, the signal is pruned immediately.</span>
                    </button>
                  </>
                )}

                {category === "ensemble" && (
                  <>
                    <div className="grid grid-cols-2 gap-3">
                      <div className="p-3 border border-hairline rounded-sm bg-surface-soft">
                        <div className="text-[10px] text-muted font-mono">TEACHER 1</div>
                        <div className="text-[13px] font-medium text-body-strong">v39d_confluence</div>
                        <span className="text-[10px] text-muted">Structural node + VPA engine.</span>
                      </div>
                      <div className="p-3 border border-hairline rounded-sm bg-surface-soft">
                        <div className="text-[10px] text-muted font-mono">TEACHER 2</div>
                        <div className="text-[13px] font-medium text-body-strong">v39b_live_adapt</div>
                        <span className="text-[10px] text-muted">Fast VPA + adaptive scaling.</span>
                      </div>
                    </div>

                    <div className="flex justify-center my-1"><ChevronRight size={18} className="text-muted rotate-90" /></div>

                    <button
                      onClick={() => setSelectedNode("ens_perf")}
                      className={`p-3 border text-left rounded-sm transition-all ${
                        selectedNode === "ens_perf" ? "border-purple-500 bg-purple-950/20 shadow-md" : "border-hairline hover:border-muted"
                      }`}
                    >
                      <div className="text-[10px] text-muted font-mono">01. MONITORING</div>
                      <div className="text-[13px] font-medium text-body-strong">Performance Feedback Loop</div>
                      <span className="text-[10px] text-muted">Tracks rolling {configParams.lookback}-bar performance metrics (returns or Sharpe ratios).</span>
                    </button>

                    <div className="flex justify-center my-1"><ChevronRight size={18} className="text-muted rotate-90" /></div>

                    <button
                      onClick={() => setSelectedNode("ens_softmax")}
                      className={`p-3 border text-left rounded-sm transition-all ${
                        selectedNode === "ens_softmax" ? "border-purple-500 bg-purple-950/20 shadow-md" : "border-hairline hover:border-muted"
                      }`}
                    >
                      <div className="text-[10px] text-muted font-mono">02. OPTIMIZATION</div>
                      <div className="text-[13px] font-medium text-body-strong">Softmax Weighting Dials</div>
                      <span className="text-[10px] text-muted">Calculates weight distributions at temperature T = {configParams.temperature}.</span>
                    </button>

                    <div className="flex justify-center my-1"><ChevronRight size={18} className="text-muted rotate-90" /></div>

                    <button
                      onClick={() => setSelectedNode("ens_consensus")}
                      className={`p-3 border text-left rounded-sm transition-all ${
                        selectedNode === "ens_consensus" ? "border-purple-500 bg-purple-950/20 shadow-md" : "border-hairline hover:border-muted"
                      }`}
                    >
                      <div className="text-[10px] text-muted font-mono">03. OUTPUT</div>
                      <div className="text-[13px] font-medium text-body-strong">Consensus Sizing & Entry</div>
                      <span className="text-[10px] text-muted">Merged portfolio weights dynamically scaling to optimal risk limits.</span>
                    </button>
                  </>
                )}

                {category === "mean_reversion" && (
                  <>
                    <div className="grid grid-cols-2 gap-3">
                      <button
                        onClick={() => setSelectedNode("mr_multirsi")}
                        className={`p-3 border text-left rounded-sm transition-all ${
                          selectedNode === "mr_multirsi" ? "border-teal-500 bg-teal-950/20 shadow-md" : "border-hairline hover:border-muted"
                        }`}
                      >
                        <div className="text-[10px] text-muted font-mono">01. INGEST</div>
                        <div className="text-[13px] font-medium text-body-strong">Multi-Window RSI</div>
                        <span className="text-[10px] text-muted">Combines short, medium and long RSI (7, 14, 28).</span>
                      </button>

                      <button
                        onClick={() => setSelectedNode("mr_trend_gate")}
                        className={`p-3 border text-left rounded-sm transition-all ${
                          selectedNode === "mr_trend_gate" ? "border-teal-500 bg-teal-950/20 shadow-md" : "border-hairline hover:border-muted"
                        }`}
                      >
                        <div className="text-[10px] text-muted font-mono">02. FILTER</div>
                        <div className="text-[13px] font-medium text-body-strong">SMA({configParams.sma_len}) Trend Filter</div>
                        <span className="text-[10px] text-muted">Locks entry to bullish-only trends (entry-only filter).</span>
                      </button>
                    </div>

                    <div className="flex justify-center my-1"><ChevronRight size={18} className="text-muted rotate-90" /></div>

                    <button
                      onClick={() => setSelectedNode("mr_ult_rsi")}
                      className={`p-3 border text-left rounded-sm transition-all ${
                        selectedNode === "mr_ult_rsi" ? "border-teal-500 bg-teal-950/20 shadow-md" : "border-hairline hover:border-muted"
                      }`}
                    >
                      <div className="text-[10px] text-muted font-mono">03. TRIGGER</div>
                      <div className="text-[13px] font-medium text-body-strong">Ultimate RSI Calculator</div>
                      <span className="text-[10px] text-muted">Weighted composite value checks for oversold condition &lt; 30.</span>
                    </button>

                    <div className="flex justify-center my-1"><ChevronRight size={18} className="text-muted rotate-90" /></div>

                    <button
                      onClick={() => setSelectedNode("mr_risk_control")}
                      className={`p-3 border text-left rounded-sm transition-all ${
                        selectedNode === "mr_risk_control" ? "border-teal-500 bg-teal-950/20 shadow-md" : "border-hairline hover:border-muted"
                      }`}
                    >
                      <div className="text-[10px] text-muted font-mono">04. SIZING</div>
                      <div className="text-[13px] font-medium text-body-strong">High-Confidence Sizing</div>
                      <span className="text-[10px] text-muted">Deploys constant position scale of {configParams.signal_scale * 100}% cash. Trailing ATR stops active.</span>
                    </button>
                  </>
                )}

                {category === "microstructure" && (
                  <>
                    <div className="grid grid-cols-4 gap-2">
                      <button
                        onClick={() => setSelectedNode("mic_ofi")}
                        className={`p-3 border text-left rounded-sm transition-all ${
                          selectedNode === "mic_ofi" ? "border-amber-500 bg-amber-950/20 shadow-md" : "border-hairline hover:border-muted"
                        }`}
                      >
                        <div className="text-[10px] text-muted font-mono">FLOW 01</div>
                        <div className="text-[13px] font-medium text-body-strong">OFI Imbalance</div>
                        <span className="text-[10px] text-muted">Signed volume EMA.</span>
                      </button>

                      <button
                        onClick={() => setSelectedNode("mic_vpin")}
                        className={`p-3 border text-left rounded-sm transition-all ${
                          selectedNode === "mic_vpin" ? "border-amber-500 bg-amber-950/20 shadow-md" : "border-hairline hover:border-muted"
                        }`}
                      >
                        <div className="text-[10px] text-muted font-mono">FLOW 02</div>
                        <div className="text-[13px] font-medium text-body-strong">VPIN Toxicity</div>
                        <span className="text-[10px] text-muted">Bucket volume toxicity.</span>
                      </button>

                      <button
                        onClick={() => setSelectedNode("mic_absorb")}
                        className={`p-3 border text-left rounded-sm transition-all ${
                          selectedNode === "mic_absorb" ? "border-amber-500 bg-amber-950/20 shadow-md" : "border-hairline hover:border-muted"
                        }`}
                      >
                        <div className="text-[10px] text-muted font-mono">FLOW 03</div>
                        <div className="text-[13px] font-medium text-body-strong">Absorption</div>
                        <span className="text-[10px] text-muted">Volume per price delta.</span>
                      </button>

                      <button
                        onClick={() => setSelectedNode("mic_sch_dev")}
                        className={`p-3 border text-left rounded-sm transition-all ${
                          selectedNode === "mic_sch_dev" ? "border-amber-500 bg-amber-950/20 shadow-md" : "border-hairline hover:border-muted"
                        }`}
                      >
                        <div className="text-[10px] text-muted font-mono">FLOW 04</div>
                        <div className="text-[13px] font-medium text-body-strong">Schedule Dev</div>
                        <span className="text-[10px] text-muted">Intraday volume anomaly.</span>
                      </button>
                    </div>

                    <div className="flex justify-center my-1"><ChevronRight size={18} className="text-muted rotate-90" /></div>

                    <button
                      onClick={() => setSelectedNode("mic_xgb")}
                      className={`p-3 border text-left rounded-sm transition-all ${
                        selectedNode === "mic_xgb" ? "border-amber-500 bg-amber-950/20 shadow-md" : "border-hairline hover:border-muted"
                      }`}
                    >
                      <div className="text-[10px] text-muted font-mono">CLASSIFICATION</div>
                      <div className="text-[13px] font-medium text-body-strong">XGBoost Meta-Classifier (Triple-Barrier Targets)</div>
                      <span className="text-[10px] text-muted">Combines point-in-time micro features to predict trade success probability.</span>
                    </button>

                    <div className="flex justify-center my-1"><ChevronRight size={18} className="text-muted rotate-90" /></div>

                    <button
                      onClick={() => setSelectedNode("mic_positioning")}
                      className={`p-3 border text-left rounded-sm transition-all ${
                        selectedNode === "mic_positioning" ? "border-amber-500 bg-amber-950/20 shadow-md" : "border-hairline hover:border-muted"
                      }`}
                    >
                      <div className="text-[10px] text-muted font-mono">VERDICT</div>
                      <div className="text-[13px] font-medium text-body-strong">Position Scale & Adaptive Invalidation</div>
                      <span className="text-[10px] text-muted">Clips entry if toxicity surges. Exits instantly if VWAP(50) breaks.</span>
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* Right Hand: Explainer Details */}
            <div className="w-full lg:w-96 flex flex-col border border-hairline bg-surface p-4 rounded-sm justify-between">
              <div>
                <h4 className="text-[13px] font-bold text-body-strong mb-2 flex items-center gap-1.5 font-sans">
                  <Info size={14} className="text-brand" /> Detailed Node Insight
                </h4>
                
                {selectedNode ? (
                  <div className="text-[13px] leading-relaxed">
                    {renderNodeDetail(selectedNode, configParams)}
                  </div>
                ) : (
                  <div className="text-muted text-[13px] flex flex-col items-center justify-center h-48 border border-dashed border-hairline rounded-sm p-4 text-center">
                    <AlertCircle size={24} className="mb-2 text-brand-muted" />
                    <p>Click on any pipeline block to inspect its technical theory and mathematical formulations.</p>
                  </div>
                )}
              </div>

              {selectedNode && (
                <div className="mt-4 pt-3 border-t border-hairline flex items-center justify-between">
                  <span className="text-[11px] text-muted font-mono">Dynamic Mode Active</span>
                  <button
                    onClick={() => setActiveTab("math")}
                    className="text-[11px] text-brand hover:underline font-medium flex items-center"
                  >
                    View All Formulas &rarr;
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 2: MATHEMATICAL FORMULATIONS */}
        {activeTab === "math" && (
          <div className="border border-hairline bg-surface p-6 rounded-sm min-h-[350px]">
            <h4 className="text-[14px] font-semibold text-body-strong mb-4 flex items-center gap-1.5 font-mono">
              <Binary size={16} className="text-brand" /> Core Mathematical Formulations
            </h4>
            
            <div className="space-y-6 text-[13px]">
              {category === "confluence" && (
                <>
                  <div className="p-4 bg-surface-soft border border-hairline rounded-sm">
                    <h5 className="font-semibold text-body-strong mb-2 font-mono">1. Volume-Price Agreement (VPA) Core</h5>
                    <p className="text-muted mb-3">
                      Measures the agreement between candle spread and trade volume. High spreads on low volume, or low spreads on high volume, indicate discrepancies that alter the VPA score.
                    </p>
                    <div className="flex flex-col gap-4 items-center bg-black/30 py-4 my-2 rounded-sm font-mono text-[14px]">
                      <div className="flex items-center">
                        <span className="text-emerald-400">Spread Score (S<sub>spread</sub>)</span>
                        <span className="mx-2">=</span>
                        <div className="inline-flex flex-col items-center align-middle">
                          <span className="border-b border-muted px-2 text-center text-body-strong">C<sub>t</sub> - O<sub>t</sub></span>
                          <span className="px-2 text-center text-muted">ATR<sub>t</sub>(14)</span>
                        </div>
                      </div>
                      
                      <div className="flex items-center">
                        <span className="text-emerald-400">Volume Score (S<sub>vol</sub>)</span>
                        <span className="mx-2">=</span>
                        <div className="inline-flex flex-col items-center align-middle">
                          <span className="border-b border-muted px-2 text-center text-body-strong">V<sub>t</sub> - SMA(V, 14)</span>
                          <span className="px-2 text-center text-muted">&sigma;<sub>V</sub>(14)</span>
                        </div>
                      </div>

                      <div className="flex items-center">
                        <span className="text-emerald-400">Composite VPA (Score<sub>vpa</sub>)</span>
                        <span className="mx-2">=</span>
                        <span className="text-body-strong">
                          S<sub>spread</sub> &times; ln(1 + |S<sub>vol</sub>|)
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="p-4 bg-surface-soft border border-hairline rounded-sm">
                    <h5 className="font-semibold text-body-strong mb-2 font-mono">2. Heikin Ashi Transformed Price</h5>
                    <p className="text-muted mb-2">
                      Smooths high-frequency price fluctuations. The engine transforms price candles into Heikin Ashi coordinates before running MACD trend signals.
                    </p>
                    <div className="flex flex-col gap-2 items-center bg-black/30 py-4 my-2 rounded-sm font-mono text-[13px]">
                      <div>HA Close (C<sub>ha</sub>) = ( O<sub>t</sub> + H<sub>t</sub> + L<sub>t</sub> + C<sub>t</sub> ) / 4</div>
                      <div>HA Open (O<sub>ha</sub>) = ( O<sub>ha, prev</sub> + C<sub>ha, prev</sub> ) / 2</div>
                      <div>HA High (H<sub>ha</sub>) = max( H<sub>t</sub>, O<sub>ha</sub>, C<sub>ha</sub> )</div>
                      <div>HA Low (L<sub>ha</sub>) = min( L<sub>t</sub>, O<sub>ha</sub>, C<sub>ha</sub> )</div>
                    </div>
                  </div>

                  <div className="p-4 bg-surface-soft border border-hairline rounded-sm">
                    <h5 className="font-semibold text-body-strong mb-2 font-mono">3. Adaptive Position Sizing Equation</h5>
                    <p className="text-muted mb-2">
                      Sizing scales dynamically based on recent trade outcomes and volume validation.
                    </p>
                    <div className="flex items-center justify-center bg-black/30 py-4 my-2 rounded-sm font-mono text-[14px]">
                      <span className="text-emerald-400 font-bold">Target Weight</span>
                      <span className="mx-2">=</span>
                      <span className="text-body-strong">
                        Base Sizing (15%) &times; f(Streak) &times; (0.5 + VPA Score)
                      </span>
                    </div>
                    <ul className="list-disc list-inside text-muted mt-2 space-y-1">
                      <li>f(Streak) multiplies allocation by <code className="text-[12px]">1 + Streak * 0.1</code> for consecutive wins.</li>
                      <li>VPA score provides a continuous scaling modifier (decaying to 0.5 under low volume-price alignment).</li>
                    </ul>
                  </div>
                </>
              )}

              {category === "arete" && (
                <>
                  <div className="p-4 bg-surface-soft border border-hairline rounded-sm">
                    <h5 className="font-semibold text-body-strong mb-2 font-mono">1. Fibonacci Retracement Gate</h5>
                    <p className="text-muted mb-3">
                      Entries must be located close to key structural retracement ratios relative to the recent high/low swing range.
                    </p>
                    
                    <div className="flex flex-col gap-3 items-center bg-black/30 py-4 my-2 rounded-sm font-mono text-[13px]">
                      <div className="flex items-center text-[14px]">
                        <span className="text-sky-400">Fib Level (FL<sub>&phi;</sub>)</span>
                        <span className="mx-2">=</span>
                        <span className="text-body-strong">SwingLow + &phi; &times; ( SwingHigh - SwingLow )</span>
                      </div>
                      
                      <div className="text-muted text-[12px]">
                        where retracement coefficient &phi; &in; &ldquo;0.382, 0.500, 0.618&rdquo;
                      </div>

                      <div className="flex items-center text-[14px] mt-2">
                        <span className="text-sky-400">Gate Condition</span>
                        <span className="mx-2">:</span>
                        <span className="text-body-strong">
                          min<sub>&phi;</sub> | Price - FL<sub>&phi;</sub> | &le; {configParams.fib_threshold} &times; ATR<sub>t</sub>
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="p-4 bg-surface-soft border border-hairline rounded-sm">
                    <h5 className="font-semibold text-body-strong mb-2 font-mono">2. Double-MA Trend Validation</h5>
                    <p className="text-muted mb-2">
                      Ensures alignment with longer-term trends. Standard entry conditions apply strict gates.
                    </p>
                    <div className="flex flex-col items-center bg-black/30 py-4 my-2 rounded-sm font-mono text-[14px]">
                      <div className="text-body-strong">
                        C<sub>t</sub> &gt; EMA(C, 200) &nbsp;&and;&nbsp; EMA(C, 50) &gt; EMA(C, 200)
                      </div>
                    </div>
                  </div>
                </>
              )}

              {category === "ensemble" && (
                <>
                  <div className="p-4 bg-surface-soft border border-hairline rounded-sm">
                    <h5 className="font-semibold text-body-strong mb-2 font-mono">1. Softmax Consensus Weighting</h5>
                    <p className="text-muted mb-3">
                      Allocates weight dynamically to teacher models based on their rolling performance metrics (such as Sharpe ratio or Return/Drawdown ratio).
                    </p>
                    
                    <div className="flex flex-col gap-4 items-center bg-black/30 py-4 my-2 rounded-sm font-mono text-[14px]">
                      <div className="flex items-center">
                        <span className="text-purple-400">Weight for Model i (W<sub>i</sub>)</span>
                        <span className="mx-2">=</span>
                        <div className="inline-flex flex-col items-center align-middle">
                          <span className="border-b border-muted px-2 text-center text-body-strong">exp( Perf<sub>i</sub> / T )</span>
                          <span className="px-2 text-center text-muted">&sum;<sub>j</sub> exp( Perf<sub>j</sub> / T )</span>
                        </div>
                      </div>
                      
                      <div className="text-muted text-[12px]">
                        where lookback window L = {configParams.lookback} bars, and temperature T = {configParams.temperature}.
                      </div>
                    </div>
                    
                    <p className="text-muted mt-2">
                      A low temperature (<code className="text-[12px]">T &rarr; 0</code>) concentrates allocation on the single best-performing model (Winner takes all). A high temperature distributes weights evenly.
                    </p>
                  </div>
                </>
              )}

              {category === "mean_reversion" && (
                <>
                  <div className="p-4 bg-surface-soft border border-hairline rounded-sm">
                    <h5 className="font-semibold text-body-strong mb-2 font-mono">1. Ultimate RSI Equation</h5>
                    <p className="text-muted mb-3">
                      Integrates short, medium, and long-term RSI values into a single weighted score to reduce false breakouts.
                    </p>
                    
                    <div className="flex flex-col items-center bg-black/30 py-4 my-2 rounded-sm font-mono text-[14px]">
                      <div className="flex items-center">
                        <span className="text-teal-400">Ultimate RSI (U)</span>
                        <span className="mx-2">=</span>
                        <div className="inline-flex flex-col items-center align-middle">
                          <span className="border-b border-muted px-2 text-center text-body-strong">4 &times; RSI<sub>t</sub>(7) + 2 &times; RSI<sub>t</sub>(14) + 1 &times; RSI<sub>t</sub>(28)</span>
                          <span className="px-2 text-center text-muted">4 + 2 + 1</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="p-4 bg-surface-soft border border-hairline rounded-sm">
                    <h5 className="font-semibold text-body-strong mb-2 font-mono">2. Entry-Only Trend Gate</h5>
                    <p className="text-muted mb-2">
                      Filters mean-reversion counter-trend entries to align with structural long-term bullish trends.
                    </p>
                    <div className="flex flex-col items-center bg-black/30 py-4 my-2 rounded-sm font-mono text-[14px]">
                      <div className="text-body-strong">
                        U &lt; 30 &nbsp;&and;&nbsp; C<sub>t</sub> &gt; SMA(C, {configParams.sma_len})
                      </div>
                    </div>
                    <p className="text-muted text-[12px] mt-2">
                      *Note: This is an <strong>entry-only</strong> filter. Once a trade is open, moving below the SMA does not trigger an exit. Exits are controlled by trailing ATR bands and a green Ultimate RSI overshoot (U &gt; 70).
                    </p>
                  </div>
                </>
              )}

              {category === "microstructure" && (
                <>
                  <div className="p-4 bg-surface-soft border border-hairline rounded-sm">
                    <h5 className="font-semibold text-body-strong mb-2 font-mono">1. Volume-price Candle Delta Proxy</h5>
                    <p className="text-muted mb-2">
                      Constructs tick-level order book flows using high-frequency OHLCV boundaries.
                    </p>
                    <div className="flex items-center justify-center bg-black/30 py-4 my-2 rounded-sm font-mono text-[14px]">
                      <span className="text-amber-400">&Delta;V<sub>t</sub> (Signed Volume Delta)</span>
                      <span className="mx-2">=</span>
                      <span className="text-body-strong">V<sub>t</sub> &times;</span>
                      <div className="inline-flex flex-col items-center align-middle mx-1">
                        <span className="border-b border-muted px-1 text-center">C<sub>t</sub> - L<sub>t</sub> - (H<sub>t</sub> - C<sub>t</sub>)</span>
                        <span className="px-1 text-center text-muted">H<sub>t</sub> - L<sub>t</sub></span>
                      </div>
                    </div>
                  </div>

                  <div className="p-4 bg-surface-soft border border-hairline rounded-sm">
                    <h5 className="font-semibold text-body-strong mb-2 font-mono">2. Order Flow Imbalance (OFI)</h5>
                    <p className="text-muted mb-2">
                      Smooths cumulative buy/sell volume pressure using an exponential moving average.
                    </p>
                    <div className="flex items-center justify-center bg-black/30 py-4 my-2 rounded-sm font-mono text-[14px]">
                      <span className="text-amber-400">OFI<sub>t</sub></span>
                      <span className="mx-2">=</span>
                      <span className="text-body-strong">
                        &alpha; &times; &Delta;V<sub>t</sub> + (1 - &alpha;) &times; OFI<sub>t-1</sub>
                      </span>
                    </div>
                  </div>

                  <div className="p-4 bg-surface-soft border border-hairline rounded-sm">
                    <h5 className="font-semibold text-body-strong mb-2 font-mono">3. Volume-Synchronized Probability of Toxicity (VPIN)</h5>
                    <p className="text-muted mb-2">
                      Calculates adverse selection risk by tracking absolute imbalance rates synchronized across constant volume buckets.
                    </p>
                    <div className="flex items-center justify-center bg-black/30 py-4 my-2 rounded-sm font-mono text-[14px]">
                      <span className="text-amber-400">VPIN</span>
                      <span className="mx-2">=</span>
                      <div className="inline-flex flex-col items-center align-middle">
                        <span className="border-b border-muted px-2 text-center text-body-strong">&sum;<sub>&tau;=1</sub><sup>N</sup> |V<sub>&tau;</sub><sup>B</sup> - V<sub>&tau;</sub><sup>S</sup>|</span>
                        <span className="px-2 text-center text-muted">N &times; V<sub>bucket</sub></span>
                      </div>
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        )}

        {/* TAB 3: LIVE STRATEGY SIMULATOR */}
        {activeTab === "simulator" && (
          <div className="border border-hairline bg-surface p-4 rounded-sm min-h-[350px]">
            <div className="flex items-center justify-between mb-4">
              <h4 className="text-[14px] font-semibold text-body-strong flex items-center gap-1.5 font-mono">
                <Sliders size={16} className="text-brand" /> Live Parameter Simulator
              </h4>
              <span className="text-[11px] text-muted bg-surface-soft border border-hairline px-2 py-0.5 rounded-sm">
                Interactive Sandbox
              </span>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* Sliders Input Panel */}
              <div className="lg:col-span-7 space-y-4">
                {category === "confluence" && (
                  <>
                    <div>
                      <div className="flex justify-between text-[12px] mb-1">
                        <span className="text-body-strong font-medium">XGBoost Hit Probability</span>
                        <span className="font-mono text-emerald-400">{(confXgb * 100).toFixed(0)}%</span>
                      </div>
                      <input
                        type="range"
                        min="0.30"
                        max="0.85"
                        step="0.01"
                        value={confXgb}
                        onChange={(e) => setConfXgb(parseFloat(e.target.value))}
                        className="w-full h-1 bg-surface-soft rounded-lg appearance-none cursor-pointer accent-brand"
                      />
                      <div className="flex justify-between text-[10px] text-muted mt-0.5">
                        <span>Threshold: {(configParams.threshold * 100).toFixed(0)}%</span>
                        <span>Max Confidence: 85%</span>
                      </div>
                    </div>

                    <div>
                      <div className="flex justify-between text-[12px] mb-1">
                        <span className="text-body-strong font-medium">VPA Score (Volume price agreement)</span>
                        <span className="font-mono text-emerald-400">{confVpa.toFixed(2)}</span>
                      </div>
                      <input
                        type="range"
                        min="-1.5"
                        max="2.0"
                        step="0.1"
                        value={confVpa}
                        onChange={(e) => setConfVpa(parseFloat(e.target.value))}
                        className="w-full h-1 bg-surface-soft rounded-lg appearance-none cursor-pointer accent-brand"
                      />
                      <div className="flex justify-between text-[10px] text-muted mt-0.5">
                        <span>Negative (Bearish)</span>
                        <span>0.0 (Neutral)</span>
                        <span>Positive (Bullish)</span>
                      </div>
                    </div>

                    <div>
                      <div className="flex justify-between text-[12px] mb-1">
                        <span className="text-body-strong font-medium">Recent Streak Multiplier</span>
                        <span className="font-mono text-emerald-400">{confStreak > 0 ? `+${confStreak}` : confStreak} consecutive</span>
                      </div>
                      <input
                        type="range"
                        min="-4"
                        max="4"
                        step="1"
                        value={confStreak}
                        onChange={(e) => setConfStreak(parseInt(e.target.value))}
                        className="w-full h-1 bg-surface-soft rounded-lg appearance-none cursor-pointer accent-brand"
                      />
                    </div>

                    <div className="flex items-center justify-between p-2 border border-hairline rounded-sm bg-surface-soft mt-2">
                      <span className="text-[12px] text-body-strong">Price Position Near Value Area Nodes</span>
                      <button
                        onClick={() => setConfInsideVa(!confInsideVa)}
                        className={`text-[11px] px-3 py-1 font-mono rounded-sm transition-all ${
                          confInsideVa ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30" : "bg-red-500/10 text-red-400 border border-red-500/20"
                        }`}
                      >
                        {confInsideVa ? "POC/VAL Support (PASS)" : "No Node Proximity (FAIL)"}
                      </button>
                    </div>
                  </>
                )}

                {category === "arete" && (
                  <>
                    <div>
                      <div className="flex justify-between text-[12px] mb-1">
                        <span className="text-body-strong font-medium">Distance to closest Fib Level</span>
                        <span className="font-mono text-sky-400">{areteFibDist.toFixed(3)} ATR</span>
                      </div>
                      <input
                        type="range"
                        min="0.0"
                        max="0.5"
                        step="0.01"
                        value={areteFibDist}
                        onChange={(e) => setAreteFibDist(parseFloat(e.target.value))}
                        className="w-full h-1 bg-surface-soft rounded-lg appearance-none cursor-pointer accent-brand"
                      />
                      <div className="flex justify-between text-[10px] text-muted mt-0.5">
                        <span>Optimal Checkpoint: 0.000</span>
                        <span>Prune Threshold: &gt; {configParams.fib_threshold} ATR</span>
                      </div>
                    </div>

                    <div className="space-y-2 mt-4">
                      <div className="flex items-center justify-between p-2.5 border border-hairline rounded-sm bg-surface-soft">
                        <div>
                          <div className="text-[12px] text-body-strong">Long-term Trend Filter</div>
                          <div className="text-[10px] text-muted">Close &gt; EMA(200) & EMA(50) &gt; EMA(200)</div>
                        </div>
                        <button
                          onClick={() => setAreteMaTrend(!areteMaTrend)}
                          className={`text-[11px] px-3 py-1 font-mono rounded-sm transition-all ${
                            areteMaTrend ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30" : "bg-red-500/10 text-red-400 border border-red-500/20"
                          }`}
                        >
                          {areteMaTrend ? "TREND BULLISH" : "TREND BEARISH"}
                        </button>
                      </div>

                      <div className="flex items-center justify-between p-2.5 border border-hairline rounded-sm bg-surface-soft">
                        <div>
                          <div className="text-[12px] text-body-strong">SOX Sector Momentum</div>
                          <div className="text-[10px] text-muted">Broad semiconductor momentum index regime</div>
                        </div>
                        <button
                          onClick={() => setAreteSoxRegime(!areteSoxRegime)}
                          className={`text-[11px] px-3 py-1 font-mono rounded-sm transition-all ${
                            areteSoxRegime ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30" : "bg-red-500/10 text-red-400 border border-red-500/20"
                          }`}
                        >
                          {areteSoxRegime ? "RISK ON (PASS)" : "RISK OFF (BLOCK)"}
                        </button>
                      </div>
                    </div>
                  </>
                )}

                {category === "ensemble" && (
                  <>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <div className="text-[12px] mb-1 font-mono">v39d Confluence Sharpe</div>
                        <div className="font-mono text-purple-400 text-[14px]">{ensSharpeA.toFixed(2)}</div>
                        <input
                          type="range"
                          min="1.0"
                          max="4.0"
                          step="0.05"
                          value={ensSharpeA}
                          onChange={(e) => setEnsSharpeA(parseFloat(e.target.value))}
                          className="w-full h-1 bg-surface-soft rounded-lg appearance-none cursor-pointer accent-brand"
                        />
                      </div>
                      <div>
                        <div className="text-[12px] mb-1 font-mono">v39b Live Adapt Sharpe</div>
                        <div className="font-mono text-purple-400 text-[14px]">{ensSharpeB.toFixed(2)}</div>
                        <input
                          type="range"
                          min="1.0"
                          max="4.0"
                          step="0.05"
                          value={ensSharpeB}
                          onChange={(e) => setEnsSharpeB(parseFloat(e.target.value))}
                          className="w-full h-1 bg-surface-soft rounded-lg appearance-none cursor-pointer accent-brand"
                        />
                      </div>
                    </div>

                    <div className="mt-4">
                      <div className="flex justify-between text-[12px] mb-1">
                        <span className="text-body-strong font-medium">Softmax Temperature (T)</span>
                        <span className="font-mono text-purple-400">{ensTemp.toFixed(2)}</span>
                      </div>
                      <input
                        type="range"
                        min="0.1"
                        max="2.0"
                        step="0.05"
                        value={ensTemp}
                        onChange={(e) => setEnsTemp(parseFloat(e.target.value))}
                        className="w-full h-1 bg-surface-soft rounded-lg appearance-none cursor-pointer accent-brand"
                      />
                      <div className="flex justify-between text-[10px] text-muted mt-0.5">
                        <span>0.1 (Strict Winner Takes All)</span>
                        <span>2.0 (Equal Weights)</span>
                      </div>
                    </div>
                  </>
                )}

                {category === "mean_reversion" && (
                  <>
                    <div className="space-y-3">
                      <div>
                        <div className="flex justify-between text-[11px] mb-0.5 font-mono">
                          <span>RSI (7 period)</span>
                          <span className="text-teal-400">{mrRsi7}</span>
                        </div>
                        <input
                          type="range"
                          min="5"
                          max="95"
                          value={mrRsi7}
                          onChange={(e) => setMrRsi7(parseInt(e.target.value))}
                          className="w-full h-1 bg-surface-soft rounded-lg appearance-none cursor-pointer accent-brand"
                        />
                      </div>

                      <div>
                        <div className="flex justify-between text-[11px] mb-0.5 font-mono">
                          <span>RSI (14 period)</span>
                          <span className="text-teal-400">{mrRsi14}</span>
                        </div>
                        <input
                          type="range"
                          min="5"
                          max="95"
                          value={mrRsi14}
                          onChange={(e) => setMrRsi14(parseInt(e.target.value))}
                          className="w-full h-1 bg-surface-soft rounded-lg appearance-none cursor-pointer accent-brand"
                        />
                      </div>

                      <div>
                        <div className="flex justify-between text-[11px] mb-0.5 font-mono">
                          <span>RSI (28 period)</span>
                          <span className="text-teal-400">{mrRsi28}</span>
                        </div>
                        <input
                          type="range"
                          min="5"
                          max="95"
                          value={mrRsi28}
                          onChange={(e) => setMrRsi28(parseInt(e.target.value))}
                          className="w-full h-1 bg-surface-soft rounded-lg appearance-none cursor-pointer accent-brand"
                        />
                      </div>
                    </div>

                    <div className="flex items-center justify-between p-2 border border-hairline rounded-sm bg-surface-soft mt-3">
                      <div>
                        <div className="text-[12px] text-body-strong">SMA({configParams.sma_len}) Filter</div>
                        <div className="text-[10px] text-muted">Price must sit above long-term trend line</div>
                      </div>
                      <button
                        onClick={() => setMrAboveSma(!mrAboveSma)}
                        className={`text-[11px] px-3 py-1 font-mono rounded-sm transition-all ${
                          mrAboveSma ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30" : "bg-red-500/10 text-red-400 border border-red-500/20"
                        }`}
                      >
                        {mrAboveSma ? "ABOVE SMA (PASS)" : "BELOW SMA (BLOCK)"}
                      </button>
                    </div>
                  </>
                )}

                {category === "microstructure" && (
                  <>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <div className="text-[11px] mb-1 font-mono">VPIN Toxic Imbalance</div>
                        <div className="font-mono text-amber-400 text-[13px]">{micVpin.toFixed(2)}</div>
                        <input
                          type="range"
                          min="0.10"
                          max="0.95"
                          step="0.01"
                          value={micVpin}
                          onChange={(e) => setMicVpin(parseFloat(e.target.value))}
                          className="w-full h-1 bg-surface-soft rounded-lg appearance-none cursor-pointer accent-brand"
                        />
                        <span className="text-[9px] text-muted">Surge &gt; 0.65 indicates risk</span>
                      </div>
                      
                      <div>
                        <div className="text-[11px] mb-1 font-mono">OFI Net Imbalance Score</div>
                        <div className="font-mono text-amber-400 text-[13px]">{micOfi.toFixed(1)}</div>
                        <input
                          type="range"
                          min="-3.0"
                          max="3.0"
                          step="0.1"
                          value={micOfi}
                          onChange={(e) => setMicOfi(parseFloat(e.target.value))}
                          className="w-full h-1 bg-surface-soft rounded-lg appearance-none cursor-pointer accent-brand"
                        />
                        <span className="text-[9px] text-muted">OFI &gt; 0.8 supports buying</span>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4 mt-3">
                      <div>
                        <div className="text-[11px] mb-1 font-mono">Volume-Price Absorption</div>
                        <div className="font-mono text-amber-400 text-[13px]">{micAbsorb.toFixed(1)}</div>
                        <input
                          type="range"
                          min="0.1"
                          max="5.0"
                          step="0.1"
                          value={micAbsorb}
                          onChange={(e) => setMicAbsorb(parseFloat(e.target.value))}
                          className="w-full h-1 bg-surface-soft rounded-lg appearance-none cursor-pointer accent-brand"
                        />
                        <span className="text-[9px] text-muted">High values confirm accumulation</span>
                      </div>

                      <div>
                        <div className="text-[11px] mb-1 font-mono">XGBoost Meta score</div>
                        <div className="font-mono text-amber-400 text-[13px]">{micXgb.toFixed(2)}</div>
                        <input
                          type="range"
                          min="0.30"
                          max="0.80"
                          step="0.01"
                          value={micXgb}
                          onChange={(e) => setMicXgb(parseFloat(e.target.value))}
                          className="w-full h-1 bg-surface-soft rounded-lg appearance-none cursor-pointer accent-brand"
                        />
                        <span className="text-[9px] text-muted">Requires &ge; 0.58 to pass</span>
                      </div>
                    </div>
                  </>
                )}
              </div>

              {/* Real-time Result Output Panel */}
              <div className="lg:col-span-5 border border-hairline bg-surface p-4 rounded-sm flex flex-col justify-between">
                <div>
                  <h5 className="text-[12px] font-mono text-muted uppercase border-b border-hairline pb-2 mb-3">
                    Calculated Engine Outputs
                  </h5>

                  {category === "confluence" && (
                    <div className="space-y-4">
                      <div>
                        <span className="text-[11px] text-muted font-mono">XGBoost Gate Status:</span>
                        <div className="flex items-center gap-2 mt-1">
                          <span className={`text-[12px] font-bold px-2 py-0.5 rounded-sm ${
                            confXgb >= configParams.threshold ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" : "bg-red-500/10 text-red-400 border border-red-500/20"
                          }`}>
                            {confXgb >= configParams.threshold ? "PASS" : "BLOCK"}
                          </span>
                          <span className="text-[12px] text-muted font-mono">
                            {(confXgb * 100).toFixed(0)}% vs {(configParams.threshold * 100).toFixed(0)}%
                          </span>
                        </div>
                      </div>

                      <div>
                        <span className="text-[11px] text-muted font-mono">Modifiers:</span>
                        <div className="grid grid-cols-2 gap-2 mt-1.5">
                          <div className="p-2 bg-surface-soft border border-hairline rounded-sm">
                            <div className="text-[9px] text-muted uppercase">VPA Sizing Mult</div>
                            <div className="text-[14px] font-bold text-body-strong font-mono">
                              {confOutputs.vpaMult.toFixed(2)}x
                            </div>
                          </div>
                          <div className="p-2 bg-surface-soft border border-hairline rounded-sm">
                            <div className="text-[9px] text-muted uppercase">Streak Mult</div>
                            <div className="text-[14px] font-bold text-body-strong font-mono">
                              {confOutputs.streakMult.toFixed(2)}x
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="pt-2">
                        <span className="text-[11px] text-muted font-mono">Verdict:</span>
                        <div className={`text-[18px] font-bold mt-1 ${
                          confOutputs.verdict === "BUY" ? "text-emerald-400" : "text-amber-500"
                        }`}>
                          {confOutputs.verdict}
                        </div>
                      </div>
                    </div>
                  )}

                  {category === "arete" && (
                    <div className="space-y-3">
                      <div>
                        <span className="text-[11px] text-muted font-mono">Gating Checklist:</span>
                        <div className="mt-2 space-y-2 text-[12px]">
                          <div className="flex items-center justify-between">
                            <span className="text-muted">1. Fibonacci Gate</span>
                            <span className={`font-mono font-semibold ${areteOutputs.fibPass ? "text-emerald-400" : "text-red-400"}`}>
                              {areteOutputs.fibPass ? "PASS" : "PRUNED"}
                            </span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-muted">2. Moving Average Gate</span>
                            <span className={`font-mono font-semibold ${areteOutputs.maPass ? "text-emerald-400" : "text-red-400"}`}>
                              {areteOutputs.maPass ? "PASS" : "PRUNED"}
                            </span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-muted">3. Sector Sentiment Gate</span>
                            <span className={`font-mono font-semibold ${areteOutputs.soxPass ? "text-emerald-400" : "text-red-400"}`}>
                              {areteOutputs.soxPass ? "PASS" : "PRUNED"}
                            </span>
                          </div>
                        </div>
                      </div>

                      <div className="pt-4 border-t border-hairline">
                        <span className="text-[11px] text-muted font-mono">Pruning Decision:</span>
                        <div className={`text-[18px] font-bold mt-1 ${
                          areteOutputs.verdict === "APPROVED" ? "text-emerald-400" : "text-red-400"
                        }`}>
                          {areteOutputs.verdict}
                        </div>
                      </div>
                    </div>
                  )}

                  {category === "ensemble" && (
                    <div className="space-y-4">
                      <div>
                        <span className="text-[11px] text-muted font-mono">Softmax Weight Splits:</span>
                        <div className="mt-3 space-y-3">
                          <div>
                            <div className="flex justify-between text-[12px] mb-1 font-mono">
                              <span>v39d_confluence (W<sub>1</sub>)</span>
                              <span className="font-bold">{(ensembleOutputs.wA * 100).toFixed(1)}%</span>
                            </div>
                            <div className="w-full bg-surface-soft h-2 rounded-full overflow-hidden">
                              <div
                                className="bg-purple-500 h-full transition-all duration-300"
                                style={{ width: `${ensembleOutputs.wA * 100}%` }}
                              />
                            </div>
                          </div>

                          <div>
                            <div className="flex justify-between text-[12px] mb-1 font-mono">
                              <span>v39b_live_adapt (W<sub>2</sub>)</span>
                              <span className="font-bold">{(ensembleOutputs.wB * 100).toFixed(1)}%</span>
                            </div>
                            <div className="w-full bg-surface-soft h-2 rounded-full overflow-hidden">
                              <div
                                className="bg-purple-500 h-full transition-all duration-300"
                                style={{ width: `${ensembleOutputs.wB * 100}%` }}
                              />
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="text-[11px] text-muted mt-2">
                        *Weights adjust dynamically relative to lookback performance. A higher Sharpe increases exponential weight scale.
                      </div>
                    </div>
                  )}

                  {category === "mean_reversion" && (
                    <div className="space-y-4">
                      <div>
                        <span className="text-[11px] text-muted font-mono">Composite Ultimate RSI:</span>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-[20px] font-bold font-mono text-teal-400">
                            {mrOutputs.ultRsi.toFixed(1)}
                          </span>
                          <span className={`text-[11px] font-bold px-2 py-0.5 rounded-sm ${
                            mrOutputs.isOversold ? "bg-teal-500/10 text-teal-400 border border-teal-500/20" : "bg-surface-soft text-muted border border-hairline"
                          }`}>
                            {mrOutputs.isOversold ? "OVERSOLD TRIGGER" : "NORMAL ZONE"}
                          </span>
                        </div>
                      </div>

                      <div>
                        <span className="text-[11px] text-muted font-mono">Entry Status:</span>
                        <div className={`text-[16px] font-bold mt-1 ${
                          mrOutputs.verdict.startsWith("BUY") ? "text-emerald-400" : "text-amber-500"
                        }`}>
                          {mrOutputs.verdict}
                        </div>
                      </div>
                    </div>
                  )}

                  {category === "microstructure" && (
                    <div className="space-y-4">
                      <div>
                        <span className="text-[11px] text-muted font-mono">Microstructure Risk Check:</span>
                        <div className="mt-2 space-y-2 text-[12px]">
                          <div className="flex items-center justify-between">
                            <span className="text-muted">Adverse Toxic Risk (VPIN)</span>
                            <span className={`font-semibold ${micOutputs.isToxic ? "text-red-400" : "text-emerald-400"}`}>
                              {micOutputs.isToxic ? "SURGING (TOXIC)" : "LOW RISK"}
                            </span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-muted">OFI Net Pressure</span>
                            <span className={`font-semibold ${micOutputs.hasBuyFlow ? "text-emerald-400" : "text-muted"}`}>
                              {micOutputs.hasBuyFlow ? "BUY ACCUMULATION" : "NEUTRAL / SELL"}
                            </span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-muted">Volume-Price Absorption</span>
                            <span className={`font-semibold ${micOutputs.isAbsorbing ? "text-emerald-400" : "text-muted"}`}>
                              {micOutputs.isAbsorbing ? "HIGH ABSORPTION" : "NORMAL"}
                            </span>
                          </div>
                        </div>
                      </div>

                      <div>
                        <span className="text-[11px] text-muted font-mono">Verdict:</span>
                        <div className={`text-[16px] font-bold mt-1 ${
                          micOutputs.verdict.includes("BUY") ? "text-emerald-400" : "text-amber-500"
                        }`}>
                          {micOutputs.verdict}
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {/* target portfolio size */}
                <div className="mt-4 pt-3 border-t border-hairline flex items-center justify-between bg-surface-soft p-2 rounded-sm">
                  <div className="flex items-center gap-1">
                    <Scale size={13} className="text-brand" />
                    <span className="text-[11px] text-muted font-mono uppercase">Target Position Size</span>
                  </div>
                  <span className="text-[16px] font-bold font-mono text-body-strong">
                    {category === "confluence" && `${(confOutputs.size * 100).toFixed(1)}%`}
                    {category === "arete" && (areteOutputs.verdict === "APPROVED" ? "Inherit Base Size" : "0.0% (PRUNED)")}
                    {category === "ensemble" && "Weighted Blended Scale"}
                    {category === "mean_reversion" && `${(mrOutputs.size * 100).toFixed(1)}%`}
                    {category === "microstructure" && `${(micOutputs.size * 100).toFixed(1)}%`}
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// Render dynamic explanations when user clicks on a flowchart node
function renderNodeDetail(nodeId: string, params: Record<string, number>) {
  switch (nodeId) {
    // Confluence Nodes
    case "ohlcv_in":
      return (
        <div className="space-y-2">
          <h5 className="font-semibold text-body-strong font-display">OHLCV Raw Data Feed</h5>
          <p className="text-muted leading-relaxed">
            The signal engine listens on 1-hour interval bars. It extracts candle range data: Open, High, Low, Close, and Volume.
          </p>
          <div className="p-2 bg-black/40 rounded-sm font-mono text-[11px] border border-hairline">
            Range ATR(14) = Rolling EMA of (High - Low)
          </div>
        </div>
      );
    case "va_nodes":
      return (
        <div className="space-y-2">
          <h5 className="font-semibold text-body-strong font-display">Value Area Node Levels</h5>
          <p className="text-muted leading-relaxed">
            Locates structural areas where significant institutional trading activity occurred. It maps the <strong>Point of Control (POC)</strong> (highest volume price level) and the <strong>Value Area Low/High (VAL/VAH)</strong> representing a 70% volume envelope.
          </p>
          <p className="text-muted leading-relaxed">
            The engine checks if the price is hovering near a support node (VAL) to initiate a buy setup.
          </p>
        </div>
      );
    case "ha_trend":
      return (
        <div className="space-y-2">
          <h5 className="font-semibold text-body-strong font-display">Heikin Ashi Trend Filters</h5>
          <p className="text-muted leading-relaxed">
            Transforms standard OHLC candles to HA candles to filter noise. It runs a Higher Time Frame (HTF) MACD on Heikin Ashi values to verify a macro bullish trend structure.
          </p>
          <div className="p-2 bg-black/40 rounded-sm font-mono text-[11px] border border-hairline">
            HA Close = (Open + High + Low + Close) / 4
          </div>
        </div>
      );
    case "vpa_score":
      return (
        <div className="space-y-2">
          <h5 className="font-semibold text-body-strong font-display">Volume-Price Analysis Score</h5>
          <p className="text-muted leading-relaxed">
            Calculates an agreement score between spread and volume based on Anna Coulling principles:
          </p>
          <div className="p-2 bg-black/40 rounded-sm font-mono text-[11px] space-y-1 border border-hairline">
            <div>Spread = (Close - Open) / ATR</div>
            <div>Vol = (Volume - SMA) / StdDev</div>
            <div>Score = Spread &times; ln(1 + |Vol|)</div>
          </div>
          <p className="text-muted leading-relaxed">
            High spread + high volume confirms strong buying pressure.
          </p>
        </div>
      );
    case "xgb_gate":
      return (
        <div className="space-y-2">
          <h5 className="font-semibold text-body-strong font-display">XGBoost Meta Probability Gate</h5>
          <p className="text-muted leading-relaxed">
            A trained XGBoost classifier evaluates the feature matrix (technical indicator values, VPA history, and node distances).
          </p>
          <p className="text-muted leading-relaxed">
            It emits a win probability. If it exceeds <strong>{(params.threshold * 100).toFixed(0)}%</strong>, the entry is unlocked.
          </p>
        </div>
      );
    case "confl_sizing":
      return (
        <div className="space-y-2">
          <h5 className="font-semibold text-body-strong font-display">Adaptive Trade Allocation</h5>
          <p className="text-muted leading-relaxed">
            Adjusts target position size based on the strength of the current VPA validation and the recent win/loss streak.
          </p>
          <div className="p-2 bg-black/40 rounded-sm font-mono text-[11px] border border-hairline">
            streak_mult = 1.0 + wins * 0.1
          </div>
        </div>
      );

    // Arete Nodes
    case "arete_input":
      return (
        <div className="space-y-2">
          <h5 className="font-semibold text-body-strong font-display">v39b Signal Trigger</h5>
          <p className="text-muted leading-relaxed">
            The core v39b engine proposes a candidate long trade. Before execution, the signal enters the Arete risk overlay pipeline.
          </p>
        </div>
      );
    case "arete_fib":
      return (
        <div className="space-y-2">
          <h5 className="font-semibold text-body-strong font-display">Fibonacci Retracement Gate</h5>
          <p className="text-muted leading-relaxed">
            Calculates Fibonacci retracement lines of the recent price swing range (e.g. 0.382, 0.50, 0.618).
          </p>
          <p className="text-muted leading-relaxed">
            To prevent chasing momentum, price must sit within <strong>{params.fib_threshold} ATR</strong> of a retracement level.
          </p>
        </div>
      );
    case "arete_ma":
      return (
        <div className="space-y-2">
          <h5 className="font-semibold text-body-strong font-display">MA Trend Direction Check</h5>
          <p className="text-muted leading-relaxed">
            Checks if price is above its 200-period Exponential Moving Average, and if the 50 EMA is above the 200 EMA, verifying macro bullish momentum.
          </p>
        </div>
      );
    case "arete_sox":
      return (
        <div className="space-y-2">
          <h5 className="font-semibold text-body-strong font-display">SOX Sector Sentiment Gate</h5>
          <p className="text-muted leading-relaxed">
            Ensures macro market indicators (like the PHLX Semiconductor Index) support a &ldquo;Risk-On&rdquo; regime. If the index displays severe bearish divergence, entries are pruned.
          </p>
        </div>
      );
    case "arete_execution":
      return (
        <div className="space-y-2">
          <h5 className="font-semibold text-body-strong font-display">Safety Consensus Decision</h5>
          <p className="text-muted leading-relaxed">
            All three checkpoints must align. If any safety gate fails, the trade is discarded, protecting portfolio equity from counter-trend traps.
          </p>
        </div>
      );

    // Ensemble Nodes
    case "ens_perf":
      return (
        <div className="space-y-2">
          <h5 className="font-semibold text-body-strong font-display">Performance Feedback Loop</h5>
          <p className="text-muted leading-relaxed">
            Dynamically records the performance results of individual teacher engines (e.g. v39b and v39d) over a rolling <strong>{params.lookback}-bar</strong> horizon.
          </p>
        </div>
      );
    case "ens_softmax":
      return (
        <div className="space-y-2">
          <h5 className="font-semibold text-body-strong font-display">Softmax Weighting Calculation</h5>
          <p className="text-muted leading-relaxed">
            Weights are computed exponentially based on historical Sharpe ratios.
          </p>
          <div className="p-2 bg-black/40 rounded-sm font-mono text-[11px] border border-hairline">
            w = exp(Sharpe / T) / sum(exp(Sharpe / T))
          </div>
          <p className="text-muted leading-relaxed">
            A temperature of <strong>{params.temperature}</strong> scales how aggressively the better-performing model is favored.
          </p>
        </div>
      );
    case "ens_consensus":
      return (
        <div className="space-y-2">
          <h5 className="font-semibold text-body-strong font-display">Consensus Sizing Output</h5>
          <p className="text-muted leading-relaxed">
            The final recommended trade weight is a performance-weighted average of the outputs from the teacher models.
          </p>
        </div>
      );

    // Mean Reversion Nodes
    case "mr_multirsi":
      return (
        <div className="space-y-2">
          <h5 className="font-semibold text-body-strong font-display">Multi-Window RSI Ingestion</h5>
          <p className="text-muted leading-relaxed">
            Listens to Relative Strength Indicators calculated over 7, 14, and 28 bars. Ingesting multiple time horizons reduces whip-saw false triggers.
          </p>
        </div>
      );
    case "mr_trend_gate":
      return (
        <div className="space-y-2">
          <h5 className="font-semibold text-body-strong font-display">SMA({params.sma_len}) Trend Filter</h5>
          <p className="text-muted leading-relaxed">
            Prevents buying declining assets. The model only issues mean-reversion buy orders if the price sits above the long-term Simple Moving Average ({params.sma_len}).
          </p>
        </div>
      );
    case "mr_ult_rsi":
      return (
        <div className="space-y-2">
          <h5 className="font-semibold text-body-strong font-display">Ultimate RSI Composition</h5>
          <p className="text-muted leading-relaxed">
            Weighted composite of three RSIs.
          </p>
          <div className="p-2 bg-black/40 rounded-sm font-mono text-[11px] border border-hairline">
            U = (4*RSI7 + 2*RSI14 + RSI28) / 7
          </div>
          <p className="text-muted leading-relaxed">
            An entry is triggered when Ultimate RSI drops below <strong>30 (oversold)</strong>.
          </p>
        </div>
      );
    case "mr_risk_control":
      return (
        <div className="space-y-2">
          <h5 className="font-semibold text-body-strong font-display">High-Confidence Sizing</h5>
          <p className="text-muted leading-relaxed">
            To achieve high win rates, this engine utilizes large capital weights (<strong>{(params.signal_scale * 100).toFixed(1)}%</strong> of cash) paired with tight trailing ATR-based stop losses.
          </p>
        </div>
      );

    // Microstructure Nodes
    case "mic_ofi":
      return (
        <div className="space-y-2">
          <h5 className="font-semibold text-body-strong font-display">Order Flow Imbalance (OFI)</h5>
          <p className="text-muted leading-relaxed">
            An indicator measuring net trade pressure. It calculates signed candle volume delta proxies (using high-low-close ticks) smoothed via an EMA.
          </p>
        </div>
      );
    case "mic_vpin":
      return (
        <div className="space-y-2">
          <h5 className="font-semibold text-body-strong font-display">VPIN Adverse Selection Risk</h5>
          <p className="text-muted leading-relaxed">
            Volume-synchronized Probability of Toxicity. Measures informed trading flow (toxic order flow) by checking absolute volume imbalances within constant volume buckets.
          </p>
        </div>
      );
    case "mic_absorb":
      return (
        <div className="space-y-2">
          <h5 className="font-semibold text-body-strong font-display">Volume-Price Absorption Ratio</h5>
          <p className="text-muted leading-relaxed">
            Checks if huge volume is being absorbed at key levels with minimal price movements. High absorption on sell pressure indicates institutional accumulation.
          </p>
        </div>
      );
    case "mic_sch_dev":
      return (
        <div className="space-y-2">
          <h5 className="font-semibold text-body-strong font-display">Volume Schedule Deviation</h5>
          <p className="text-muted leading-relaxed">
            Measures how much the current bar&apos;s volume deviates from the typical historical intraday profile. Surges suggest institutional participation.
          </p>
        </div>
      );
    case "mic_xgb":
      return (
        <div className="space-y-2">
          <h5 className="font-semibold text-body-strong font-display">XGBoost Meta Classifier</h5>
          <p className="text-muted leading-relaxed">
            Maps VPIN, OFI, Absorption, and Schedule deviations into a trained gradient boosted tree model. The tree is trained using triple-barrier labeling (Profit Target, Stop Loss, Max Hold time limit).
          </p>
        </div>
      );
    case "mic_positioning":
      return (
        <div className="space-y-2">
          <h5 className="font-semibold text-body-strong font-display">Execution Invalidation Control</h5>
          <p className="text-muted leading-relaxed">
            If VPIN surges (toxicity high), the position is scaled down to avoid toxic adverse selection. If price breaks below the rolling VWAP(50) line, the trade is terminated immediately.
          </p>
        </div>
      );

    default:
      return <p className="text-muted">No technical detail registered for this node.</p>;
  }
}
