"use client";

import type { ReactNode } from "react";
import { motion } from "framer-motion";
import {
  Activity,
  Award,
  ShieldAlert,
  ListChecks,
  Zap,
  TrendingUp,
  TrendingDown,
  Compass,
  Info,
  AlertTriangle,
  Layers,
  Sliders,
  LineChart
} from "lucide-react";
import { ActionChip } from "@/components/ui/ActionChip";
import { Stat } from "@/components/ui/Stat";
import { ModelFlow } from "@/components/models/ModelFlow";
import type {
  AnalysisDecision,
  AnalysisReport as AnalysisReportType,
} from "@/lib/types";

function fmt(n: number | null | undefined, digits = 2): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return n.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function fmtUsd(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

function fmtPct(n: number | null | undefined, digits = 1): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}

function impactColor(impact: string): string {
  if (impact === "positive") return "var(--td-success)";
  if (impact === "negative") return "var(--td-m-red)";
  return "var(--td-muted)";
}

function driverLabelColor(impact: string): string {
  if (impact === "positive") return "var(--td-success)";
  if (impact === "negative") return "var(--td-m-red)";
  return "var(--td-ink-400)";
}

function TraceItem({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex flex-col p-2 bg-neutral-900/40 rounded border border-neutral-900">
      <span className="text-[10px] uppercase tracking-wider" style={{ color: "var(--td-ink-500)" }}>
        {label}
      </span>
      <span className="text-[12px] tabular mt-0.5 font-medium" style={{ fontFamily: "var(--td-font-mono)", color: "var(--td-ink-200)" }}>
        {value}
      </span>
    </div>
  );
}

function VisualLevelsSlider({ entry, stop, target, price }: { entry: number; stop: number; target: number; price: number }) {
  // Map values onto a percentage scale relative to stop and target
  const minVal = Math.min(stop, entry, target, price) * 0.995;
  const maxVal = Math.max(stop, entry, target, price) * 1.005;
  const range = maxVal - minVal;
  const pct = (val: number) => {
    if (range === 0) return 50;
    return Math.max(2, Math.min(98, ((val - minVal) / range) * 100));
  };

  const isLong = target > stop;

  return (
    <div className="my-5 p-4 rounded-lg bg-neutral-900/60 border border-neutral-800/80">
      <span className="text-[10px] uppercase tracking-wider text-neutral-500 font-mono mb-3 block">
        Visual Risk-Reward Map ({isLong ? "Long Strategy" : "Short Strategy"})
      </span>
      <div className="relative w-full h-8 flex items-center">
        {/* Track Line */}
        <div className="absolute left-0 right-0 h-1.5 rounded-full bg-neutral-800 overflow-hidden">
          {/* Active zone coloring (Entry to Target) */}
          <div 
            className={`absolute h-full ${isLong ? "bg-green-500/30" : "bg-red-500/30"}`} 
            style={{ 
              left: `${Math.min(pct(entry), pct(target))}%`, 
              width: `${Math.abs(pct(target) - pct(entry))}%` 
            }} 
          />
          {/* Risk zone coloring (Stop to Entry) */}
          <div 
            className="absolute h-full bg-red-500/50" 
            style={{ 
              left: `${Math.min(pct(stop), pct(entry))}%`, 
              width: `${Math.abs(pct(entry) - pct(stop))}%` 
            }} 
          />
        </div>

        {/* Invalidation/Stop Point */}
        <div className="absolute flex flex-col items-center z-10" style={{ left: `${pct(stop)}%`, transform: 'translateX(-50%)' }}>
          <div className="w-3.5 h-3.5 rounded bg-red-500 border border-neutral-950 flex items-center justify-center text-[8px] font-bold text-white shadow-lg">S</div>
          <span className="text-[9px] font-mono text-red-400 mt-1.5 font-semibold bg-neutral-950/80 px-1 rounded border border-red-500/20">{fmtUsd(stop)}</span>
        </div>

        {/* Current Price Marker */}
        {price !== entry && (
          <div className="absolute flex flex-col items-center z-20" style={{ left: `${pct(price)}%`, transform: 'translateX(-50%)' }}>
            <div className="w-2.5 h-2.5 rounded-full bg-white border border-neutral-950 shadow-md animate-pulse" />
            <span className="text-[9px] font-mono text-white mt-2 bg-neutral-950/90 px-1.5 py-0.5 rounded border border-neutral-800">Spot: {fmtUsd(price)}</span>
          </div>
        )}

        {/* Entry Marker */}
        <div className="absolute flex flex-col items-center z-10" style={{ left: `${pct(entry)}%`, transform: 'translateX(-50%)' }}>
          <div className="w-3.5 h-3.5 rounded-full bg-blue-500 border border-neutral-950 flex items-center justify-center text-[8px] font-bold text-white shadow-lg">E</div>
          <span className="text-[9px] font-mono text-blue-400 mt-1.5 font-semibold bg-neutral-950/80 px-1 rounded border border-blue-500/20">{fmtUsd(entry)}</span>
        </div>

        {/* Target Marker */}
        <div className="absolute flex flex-col items-center z-10" style={{ left: `${pct(target)}%`, transform: 'translateX(-50%)' }}>
          <div className="w-3.5 h-3.5 rounded bg-green-500 rotate-45 border border-neutral-950 flex items-center justify-center text-[8px] font-bold text-white shadow-lg shadow-green-950/20">
            <span className="rotate-[-45deg]">T</span>
          </div>
          <span className="text-[9px] font-mono text-green-400 mt-1.5 font-semibold bg-neutral-950/80 px-1 rounded border border-green-500/20">{fmtUsd(target)}</span>
        </div>
      </div>
    </div>
  );
}

function LevelsPanel({ decision }: { decision: AnalysisDecision }) {
  const s = decision.sizing;
  if (!s || s.entry == null || s.stop == null) {
    return (
      <div className="p-4 rounded-lg bg-neutral-900/30 border border-neutral-800 text-center">
        <p className="text-[13px] text-neutral-400 flex items-center justify-center gap-2">
          <Info size={14} />
          No execution levels available — the model did not emit stop/entry coordinates.
        </p>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 md:grid-cols-6">
        <Stat label="Spot Price" value={fmtUsd(s.price)} emphasize />
        <Stat label="Entry Trigger" value={fmtUsd(s.entry)} emphasize />
        <Stat label="Stop Loss" value={fmtUsd(s.stop)} emphasize />
        <Stat label="Target (2R)" value={fmtUsd(s.target)} emphasize />
        <Stat label="Risk / Share" value={fmtUsd(s.risk_per_share)} emphasize />
        <Stat label="Position Shares" value={s.shares ?? "—"} emphasize />
        <Stat label="Notional Value" value={fmtUsd(s.notional)} emphasize />
        <Stat label="Max Loss Budget" value={fmtUsd(decision.max_loss_dollars)} emphasize />
        <Stat label="Sleeve Risk %" value={fmtPct(decision.risk_pct, 2)} emphasize />
        <Stat label="Sleeve Direction" value={s.side ? s.side.toUpperCase() : "—"} emphasize />
        <Stat label="Conviction Score" value={fmt(decision.conviction, 4)} emphasize />
        <Stat label="Blended Confidence" value={fmt(decision.blended_confidence, 4)} emphasize />
      </div>

      <VisualLevelsSlider 
        entry={s.entry ?? 0} 
        stop={s.stop ?? 0} 
        target={s.target ?? s.entry ?? 0} 
        price={s.price ?? s.entry ?? 0} 
      />
    </div>
  );
}

function DecisionTrace({ decision }: { decision: AnalysisDecision }) {
  const c = decision.confidence;
  return (
    <div className="mt-4 flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <TraceItem label="Confidence State" value={c?.state ?? "—"} />
        <TraceItem label="Probability Band" value={c?.band ?? "—"} />
        <TraceItem label="Raw Probability" value={fmt(c?.raw_probability, 4)} />
        <TraceItem label="Calibrated Proba" value={fmt(c?.calibrated_probability, 4)} />
        <TraceItem label="Size Limit" value={fmt(c?.size_limit, 4)} />
        <TraceItem label="Blended Value" value={fmt(decision.blended_confidence, 4)} />
        <TraceItem label="Applied Risk %" value={fmtPct(decision.risk_pct, 2)} />
        <TraceItem label="Max Dollar Loss" value={fmtUsd(decision.max_loss_dollars)} />
      </div>
      
      <div className="mt-2 grid grid-cols-1 gap-4 lg:grid-cols-2">
        {c?.evidence && c.evidence.length > 0 ? (
          <div className="p-3 rounded bg-neutral-950/40 border border-neutral-900">
            <span className="td-label text-[10px] text-neutral-400 block mb-2 font-semibold">Evidence Details</span>
            <ul className="flex flex-col gap-1 list-none p-0 m-0">
              {c.evidence.map((e, i) => (
                <li key={`evidence-${i}`} className="text-[11px] tabular text-neutral-300 font-mono leading-relaxed flex items-start gap-1.5">
                  <span className="text-neutral-600 shrink-0 select-none">→</span>
                  <span>{e}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {c?.failed_checks && c.failed_checks.length > 0 ? (
          <div className="p-3 rounded bg-red-950/10 border border-red-900/30">
            <span className="td-label text-[10px] text-red-400 block mb-2 font-semibold flex items-center gap-1.5">
              <ShieldAlert size={12} />
              Failed Safety Checks
            </span>
            <ul className="flex flex-col gap-1 list-none p-0 m-0">
              {c.failed_checks.map((r, i) => (
                <li key={`fail-${i}`} className="text-[11px] text-red-200 leading-relaxed flex items-start gap-1.5 font-mono">
                  <span className="text-red-500 shrink-0">✕</span>
                  <span>{r}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {c?.reasons && c.reasons.length > 0 ? (
          <div className="p-3 rounded bg-neutral-950/40 border border-neutral-900 col-span-full">
            <span className="td-label text-[10px] text-neutral-400 block mb-2 font-semibold">Deciding Constraints</span>
            <ul className="grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-1 list-none p-0 m-0 font-mono text-[11px] text-neutral-300">
              {c.reasons.map((r, i) => (
                <li key={`creason-${i}`} className="flex items-start gap-1.5 leading-relaxed">
                  <span className="text-neutral-500">•</span>
                  <span>{r.replace(/_/g, " ")}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </div>
  );
}

type AnalysisReportProps = {
  symbol: string;
  model: string | null;
  report: AnalysisReportType;
};

export function AnalysisReport({ symbol, model, report }: AnalysisReportProps) {
  const { facts, decision, suggestion } = report;
  const live = facts.live;
  const macro = facts.macro;
  const gex = facts.gex;
  const m = facts.model;
  const ticket = suggestion.ticket;
  const analysisAction = decision.analysis_action || decision.action || "WAIT";
  const confState = decision.confidence_state || "ABSTAIN";
  
  const execBlocked =
    decision.execution_blocked === true ||
    (confState !== "ENTER" && confState !== "—");

  const gateLabel =
    confState === "ENTER"
      ? "EXECUTION READY"
      : confState === "WATCH"
        ? "WATCH — NO EXECUTION YET"
        : "EXECUTION BLOCKED";

  // Visual helper for GEX position
  const spot = gex.spot ?? facts.price ?? 0;
  const putWall = gex.put_wall ?? spot;
  const callWall = gex.call_wall ?? spot;
  const flip = gex.approx_flip_strike ?? spot;

  const minGex = Math.min(putWall, spot) * 0.985;
  const maxGex = Math.max(callWall, spot) * 1.015;
  const gexRange = maxGex - minGex;
  const gexPct = (val: number) => {
    if (gexRange === 0) return 50;
    return Math.max(3, Math.min(97, ((val - minGex) / gexRange) * 100));
  };

  // Model Leaderboard score helpers
  const maxScore = Math.max(...facts.top_models.map((x) => x.score || 1), 1);

  // Animation constants
  const containerVariants = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: {
        staggerChildren: 0.08
      }
    }
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 12 },
    show: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 100 } }
  };

  return (
    <motion.div 
      className="flex flex-col gap-4 text-white"
      variants={containerVariants}
      initial="hidden"
      animate="show"
    >
      {/* ========================================== */}
      {/* SECTION 1: DATA PRIMACY (Facts & Metrics)  */}
      {/* ========================================== */}

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Market Facts & Live indicators */}
        <motion.section className="td-panel flex flex-col gap-3 p-5" variants={itemVariants}>
          <div className="flex items-center justify-between border-b border-neutral-800/60 pb-3">
            <h2 className="text-[14px] font-medium flex items-center gap-2" style={{ color: "var(--td-ink-100)" }}>
              <Activity className="text-blue-400" size={16} />
              Market Data & Regimes
            </h2>
            <span className="text-[10px] font-mono text-neutral-500">
              As-of: {facts.asof_utc}
            </span>
          </div>

          <div className="flex flex-col md:flex-row md:items-center gap-4 py-2 border-b border-dashed border-neutral-800">
            <div className="flex flex-col p-3 rounded-lg border border-neutral-800/80 bg-neutral-950/60 shrink-0">
              <span className="text-[10px] uppercase tracking-wider text-neutral-500 font-mono">Spot Price</span>
              <span className="text-[26px] font-mono font-bold tracking-tight text-white mt-1">
                {facts.price ? fmtUsd(facts.price) : "—"}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-3 w-full">
              <div className="flex items-center gap-2.5 p-2 bg-neutral-900/30 rounded border border-neutral-900">
                <span className={`h-2.5 w-2.5 rounded-full ${live.above_vwap ? "bg-green-500 shadow-[0_0_8px_var(--td-success)]" : "bg-red-500"}`} />
                <span className="text-[12px] font-medium text-neutral-300">
                  {live.above_vwap ? "Above VWAP" : "Below VWAP"}
                </span>
              </div>
              <div className="flex items-center gap-2.5 p-2 bg-neutral-900/30 rounded border border-neutral-900">
                {live.macd_positive ? (
                  <TrendingUp className="text-green-500" size={14} />
                ) : (
                  <TrendingDown className="text-red-500" size={14} />
                )}
                <span className="text-[12px] font-medium text-neutral-300">
                  MACD {live.macd_positive ? "Positive" : "Negative"}
                </span>
              </div>
              <div className="flex items-center gap-2.5 p-2 bg-neutral-900/30 rounded border border-neutral-900">
                <span className={`h-2.5 w-2.5 rounded-full ${live.swing_uptrend ? "bg-green-500" : "bg-red-500"}`} />
                <span className="text-[12px] font-medium text-neutral-300">
                  Swing: {live.swing_uptrend ? "Uptrend" : "Downtrend"}
                </span>
              </div>
              <div className="flex items-center gap-2.5 p-2 bg-neutral-900/30 rounded border border-neutral-900">
                <TrendingUp className="text-neutral-400" size={14} />
                <span className="text-[12px] font-medium text-neutral-300">
                  QQQ: {macro.qqq_trend || "—"}
                </span>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 md:grid-cols-4 mt-2">
            <Stat label="Vol Z-Score" value={fmt(live.vol_z, 2)} emphasize />
            <Stat label="ATR Percentage" value={fmtPct(live.atr_pct, 2)} emphasize />
            <Stat label="Signal Strength" value={`${fmt(live.signal_strength, 1)} / 10`} emphasize />
            <Stat label="XLP / SPY Ratio" value={macro.xlp_spy_ratio_state || "—"} emphasize />
          </div>

          <div className="mt-2 pt-3 border-t border-neutral-800/60 grid grid-cols-2 md:grid-cols-3 gap-2">
            <div className="text-[11px] text-neutral-400 flex items-center gap-1.5">
              <span className="font-semibold text-neutral-500 font-mono">MODEL RUN:</span>
              <span className="font-mono text-neutral-200 truncate">{m.model || "—"}</span>
            </div>
            <div className="text-[11px] text-neutral-400 flex items-center gap-1.5">
              <span className="font-semibold text-neutral-500 font-mono">MODEL CONFIDENCE:</span>
              <span className="font-mono text-neutral-200">{fmtPct(m.confidence, 1)}</span>
            </div>
            <div className="text-[11px] text-neutral-400 flex items-center gap-1.5 col-span-2 md:col-span-1">
              <span className="font-semibold text-neutral-500 font-mono">SETUP OK:</span>
              <span className={`font-mono font-semibold ${m.setup_ok ? "text-green-400" : "text-red-400"}`}>
                {m.setup_ok ? "PASSED" : "FAILED"}
              </span>
            </div>
          </div>
        </motion.section>

        {/* Gamma Exposure / Levels map */}
        <motion.section className="td-panel flex flex-col gap-3 p-5" variants={itemVariants}>
          <div className="flex items-center justify-between border-b border-neutral-800/60 pb-3">
            <h2 className="text-[14px] font-medium flex items-center gap-2" style={{ color: "var(--td-ink-100)" }}>
              <LineChart className="text-violet-400" size={16} />
              Gamma Regimes & Option Chain Walls
            </h2>
            <span className={`text-[10px] font-bold px-2 py-0.5 rounded font-mono uppercase bg-neutral-900 border ${gex.regime === "positive" ? "text-green-400 border-green-500/20" : gex.regime === "negative" ? "text-red-400 border-red-500/20" : "text-neutral-400 border-neutral-800"}`}>
              {gex.regime || "UNKNOWN"} GAMMA
            </span>
          </div>

          <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4 py-1">
            <Stat label="Call Wall" value={fmtUsd(gex.call_wall)} emphasize />
            <Stat label="Put Wall" value={fmtUsd(gex.put_wall)} emphasize />
            <Stat label="Flip Strike" value={fmtUsd(gex.approx_flip_strike)} emphasize />
            <Stat label="Max Pain Strike" value={fmtUsd(gex.max_pain)} emphasize />
            <Stat label="Expected Move" value={gex.expected_move_pct ? `±${fmtPct(gex.expected_move_pct, 2)}` : "—"} />
            <Stat label="Squeeze Signal" value={gex.squeeze_label ? gex.squeeze_label.toUpperCase() : "NEUTRAL"} />
            <Stat label="Squeeze Score" value={fmt(gex.squeeze_score, 1)} />
            <Stat label="Spot Strike" value={fmtUsd(gex.spot)} />
          </div>

          {/* Horizontal Option Wall map */}
          {gex.put_wall || gex.call_wall || gex.approx_flip_strike ? (
            <div className="mt-4 p-4 rounded-lg bg-neutral-950/65 border border-neutral-900">
              <span className="text-[9px] uppercase tracking-wider text-neutral-500 font-mono block mb-3">
                Option Chain Wall Map (Visual Support)
              </span>
              <div className="relative w-full h-8 flex items-center">
                {/* Visual Line */}
                <div className="absolute left-0 right-0 h-1 bg-neutral-800 rounded-full" />
                
                {/* Flip area marker */}
                {flip && (
                  <div className="absolute h-1 bg-violet-500/30" style={{ left: `0%`, width: `${gexPct(flip)}%` }} />
                )}

                {gex.put_wall && (
                  <div className="absolute flex flex-col items-center" style={{ left: `${gexPct(putWall)}%`, transform: "translateX(-50%)" }}>
                    <div className="w-2.5 h-2.5 rounded-full bg-red-500 border border-neutral-950 shadow-md" />
                    <span className="text-[8px] font-mono text-red-400 mt-1 font-bold">Put Wall</span>
                    <span className="text-[8px] font-mono text-neutral-500">{fmtUsd(gex.put_wall)}</span>
                  </div>
                )}

                {gex.approx_flip_strike && (
                  <div className="absolute flex flex-col items-center" style={{ left: `${gexPct(flip)}%`, transform: "translateX(-50%)" }}>
                    <div className="w-2 h-2 rounded bg-violet-500 border border-neutral-950 shadow-md rotate-45" />
                    <span className="text-[8px] font-mono text-violet-400 mt-1 font-bold">Vol Flip</span>
                    <span className="text-[8px] font-mono text-neutral-500">{fmtUsd(gex.approx_flip_strike)}</span>
                  </div>
                )}

                {spot && (
                  <div className="absolute flex flex-col items-center z-10" style={{ left: `${gexPct(spot)}%`, transform: "translateX(-50%)" }}>
                    <div className="w-3 h-3 rounded-full bg-white border border-neutral-950 shadow-lg animate-pulse" />
                    <span className="text-[8px] font-mono text-white mt-1 bg-neutral-900 px-1 py-0.5 rounded border border-neutral-700 font-bold">Spot</span>
                    <span className="text-[8px] font-mono text-neutral-400">{fmtUsd(spot)}</span>
                  </div>
                )}

                {gex.call_wall && (
                  <div className="absolute flex flex-col items-center" style={{ left: `${gexPct(callWall)}%`, transform: "translateX(-50%)" }}>
                    <div className="w-2.5 h-2.5 rounded-full bg-green-500 border border-neutral-950 shadow-md" />
                    <span className="text-[8px] font-mono text-green-400 mt-1 font-bold">Call Wall</span>
                    <span className="text-[8px] font-mono text-neutral-500">{fmtUsd(gex.call_wall)}</span>
                  </div>
                )}
              </div>
            </div>
          ) : null}
        </motion.section>
      </div>

      {/* Model Leaderboard */}
      <motion.section className="td-panel p-5" variants={itemVariants}>
        <div className="flex items-center justify-between border-b border-neutral-800/60 pb-3 mb-3">
          <h2 className="text-[14px] font-medium flex items-center gap-2" style={{ color: "var(--td-ink-100)" }}>
            <Award className="text-yellow-400" size={16} />
            Top Performing Models for {symbol}
          </h2>
          <span className="text-[10px] text-neutral-400 font-mono">
            Horizon-ranked catalog
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left" style={{ fontSize: "12.5px" }}>
            <thead>
              <tr className="text-neutral-500 font-mono border-b border-neutral-800/80 text-[11px] uppercase tracking-wider">
                <th className="py-2 pr-3 font-semibold w-12">Rank</th>
                <th className="py-2 pr-3 font-semibold">Model Identifier</th>
                <th className="py-2 pr-3 font-semibold text-right">Win Rate</th>
                <th className="py-2 pr-3 font-semibold text-right">Sharpe</th>
                <th className="py-2 pr-3 font-semibold text-right">Return</th>
                <th className="py-2 pr-3 font-semibold text-right">Drawdown</th>
                <th className="py-2 pr-3 font-semibold text-right">Trades</th>
                <th className="py-2 pr-3 font-semibold text-right w-36">Blended Score</th>
              </tr>
            </thead>
            <tbody style={{ color: "var(--td-ink-200)" }}>
              {facts.top_models.map((row, idx) => {
                const isActive = row.model === model;
                const scorePercentage = Math.max(5, Math.min(100, (row.score / maxScore) * 100));
                
                return (
                  <tr 
                    key={row.model} 
                    className={`border-t border-neutral-900 transition-colors hover:bg-neutral-900/30 ${isActive ? "bg-blue-500/5 hover:bg-blue-500/10" : ""}`}
                  >
                    <td className="py-2.5 pr-3 font-mono font-semibold">
                      {idx === 0 ? "🥇" : idx === 1 ? "🥈" : idx === 2 ? "🥉" : `${row.rank}`}
                    </td>
                    <td className="py-2.5 pr-3 font-mono">
                      <div className="flex items-center gap-2">
                        <span className={isActive ? "text-blue-400 font-bold" : "text-neutral-200"}>
                          {row.model}
                        </span>
                        {isActive && (
                          <span className="text-[9px] uppercase tracking-wider px-1 bg-blue-500/20 text-blue-400 border border-blue-500/30 rounded font-sans">
                            Selected
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="py-2.5 pr-3 text-right font-mono font-medium">{fmtPct(row.win_rate, 1)}</td>
                    <td className="py-2.5 pr-3 text-right font-mono">{fmt(row.sharpe, 2)}</td>
                    <td className="py-2.5 pr-3 text-right font-mono text-green-400 font-semibold">{fmtPct(row.total_return, 1)}</td>
                    <td className="py-2.5 pr-3 text-right font-mono text-red-400">{fmtPct(row.max_drawdown, 1)}</td>
                    <td className="py-2.5 pr-3 text-right font-mono text-neutral-400">{row.trade_count ?? "—"}</td>
                    <td className="py-2.5 pr-3 text-right font-mono">
                      <div className="flex items-center justify-end gap-2.5">
                        <span className="text-[12px] font-bold text-white min-w-[35px] text-right">
                          {fmt(row.score, 3)}
                        </span>
                        <div className="w-16 h-1.5 bg-neutral-800 rounded-full overflow-hidden shrink-0 hidden sm:block">
                          <div 
                            className={`h-full ${idx === 0 ? "bg-gradient-to-r from-yellow-600 to-yellow-400" : "bg-blue-500"}`}
                            style={{ width: `${scorePercentage}%` }}
                          />
                        </div>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </motion.section>


      {/* ========================================== */}
      {/* SECTION 2: READS & SUGGESTIONS (Middle)    */}
      {/* ========================================== */}

      <div className="grid gap-4 lg:grid-cols-3">
        {/* AI Verdict, Gate & Rationale */}
        <motion.section className="td-panel p-5 lg:col-span-2 flex flex-col gap-4" variants={itemVariants}>
          <div className="flex items-center justify-between border-b border-neutral-800/60 pb-3">
            <h2 className="text-[14px] font-medium flex items-center gap-2" style={{ color: "var(--td-ink-100)" }}>
              <Compass className="text-emerald-400" size={16} />
              AI Agent Verdict & Setup Rationale
            </h2>
            <span className="text-[10px] text-neutral-500 uppercase tracking-widest font-mono">
              READ
            </span>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 p-4 rounded-lg bg-neutral-950/65 border border-neutral-900">
            <div className="flex items-center gap-3">
              <span className="text-[11px] font-mono text-neutral-400 uppercase tracking-wider">Analysis Setup</span>
              <ActionChip action={analysisAction} size="lg" />
            </div>

            <div className="flex items-center gap-3">
              <span className="text-[11px] font-mono text-neutral-400 uppercase tracking-wider">Risk Gate</span>
              <span className={`text-[12px] font-mono font-bold px-3 py-1 rounded flex items-center gap-2 border ${
                confState === "ENTER" 
                  ? "bg-green-500/10 text-green-400 border-green-500/30" 
                  : confState === "WATCH"
                    ? "bg-yellow-500/10 text-yellow-400 border-yellow-500/30"
                    : "bg-red-500/10 text-red-400 border-red-500/30"
              }`}>
                <span className={`h-2 w-2 rounded-full ${
                  confState === "ENTER" ? "bg-green-500 animate-pulse" : confState === "WATCH" ? "bg-yellow-500 animate-pulse" : "bg-red-500"
                }`} />
                {gateLabel}
              </span>
            </div>
          </div>

          {/* Rationale Blockquote */}
          <div className="border-l-4 border-blue-500 bg-blue-500/[0.03] pl-4 py-3 pr-2 italic text-[14.5px] text-neutral-200 rounded-r-md leading-relaxed">
            &ldquo;{suggestion.rationale}&rdquo;
          </div>

          {/* Sizing, Levels & Sizing Visualizer */}
          <div className="mt-2">
            <span className="td-label text-[11px] text-neutral-400 uppercase block mb-3 font-semibold">
              Execution Level Specifications {execBlocked ? "(Support Model Only)" : ""}
            </span>
            <LevelsPanel decision={decision} />
          </div>

          {execBlocked && (
            <div className="flex items-start gap-2.5 p-3.5 rounded bg-red-950/10 border border-red-900/30 text-[12px] leading-relaxed text-red-200">
              <ShieldAlert className="text-red-400 shrink-0 mt-0.5" size={15} />
              <div>
                <strong className="text-red-300 font-semibold block mb-0.5">Execution Blocked by Risk Manager</strong>
                Levels and share sizing mathematical outcomes displayed above are illustrative guidelines. Do not submit orders unless the risk gate transitions to ENTER.
                {decision.confidence?.reasons?.length ? (
                  <span className="block mt-1.5 font-mono text-[11px] text-red-300/80">
                    Reasons: {decision.confidence.reasons.slice(0, 3).join(", ").replace(/_/g, " ")}.
                  </span>
                ) : null}
              </div>
            </div>
          )}
        </motion.section>

        {/* Suggestion Steps Checklist & Invalidation */}
        <motion.section className="td-panel p-5 flex flex-col gap-4" variants={itemVariants}>
          <div className="flex items-center justify-between border-b border-neutral-800/60 pb-3">
            <h2 className="text-[14px] font-medium flex items-center gap-2" style={{ color: "var(--td-ink-100)" }}>
              <ListChecks className="text-blue-400" size={16} />
              Operator Suggestion Steps
            </h2>
            <span className="text-[10px] text-neutral-500 font-mono">
              Action Steps
            </span>
          </div>

          <div className="flex flex-col gap-3 py-1">
            <div className="flex items-center justify-between p-2 rounded bg-neutral-900/30 border border-neutral-900 text-[12px] font-mono text-neutral-300">
              <span>Primary Path</span>
              <span className="text-blue-400 font-bold uppercase">{ticket.mode} · {ticket.vehicle}</span>
            </div>

            <ol className="flex flex-col gap-3 list-none p-0 m-0">
              {ticket.steps && ticket.steps.length > 0 ? (
                ticket.steps.map((s, i) => (
                  <li 
                    key={`step-${i}`} 
                    className="flex gap-3 text-[13px] leading-snug p-2.5 rounded bg-neutral-950/40 border border-neutral-900 hover:border-neutral-800 transition-colors"
                  >
                    <span className="flex items-center justify-center w-5 h-5 rounded-full bg-blue-500/10 text-blue-400 text-[11px] border border-blue-500/20 font-mono shrink-0 font-bold">
                      {i + 1}
                    </span>
                    <span className="text-neutral-200 pt-0.5">{s}</span>
                  </li>
                ))
              ) : (
                <li className="text-[13px] text-neutral-400 py-3 text-center">
                  No active instruction steps emitted.
                </li>
              )}
            </ol>
          </div>

          {/* Alternatives/Invalidation criteria */}
          <div className="border-t border-neutral-800/60 pt-4 mt-auto">
            <h3 className="text-[12px] font-semibold text-neutral-300 flex items-center gap-1.5 mb-2.5 font-mono uppercase tracking-wider">
              <AlertTriangle className="text-yellow-500" size={13} />
              What would invalidate this setup
            </h3>
            <ul className="flex flex-col gap-2 list-none p-0 m-0 text-[12.5px] text-neutral-300">
              {suggestion.alternatives.map((a, i) => (
                <li key={`alt-${i}`} className="flex items-start gap-2 bg-neutral-900/25 p-2 rounded border border-neutral-900/40 leading-normal">
                  <span className="text-yellow-500/70 font-semibold shrink-0 mt-0.5">⚠️</span>
                  <span>{a}</span>
                </li>
              ))}
            </ul>
          </div>
        </motion.section>
      </div>

      {/* Decision Factors & Trace Panel */}
      <div className="grid gap-4 lg:grid-cols-3">
        {/* Drivers */}
        <motion.section className="td-panel p-5 flex flex-col gap-3" variants={itemVariants}>
          <div className="flex items-center justify-between border-b border-neutral-800/60 pb-3 mb-2">
            <h2 className="text-[14px] font-medium flex items-center gap-2" style={{ color: "var(--td-ink-100)" }}>
              <Layers className="text-amber-400" size={16} />
              Decision Drivers & Weights
            </h2>
            <span className="text-[10px] text-neutral-500 font-mono">
              Sensors
            </span>
          </div>

          <div className="flex flex-col gap-3">
            {suggestion.drivers.map((d, i) => {
              const isPositive = d.impact === "positive";
              const isNegative = d.impact === "negative";
              const val = d.value;
              
              return (
                <div 
                  key={`driver-${i}`} 
                  className="flex flex-col gap-1.5 p-3 rounded bg-neutral-950/45 border border-neutral-900 hover:border-neutral-800/80 transition-colors"
                >
                  <div className="flex items-center justify-between text-[12.5px]">
                    <span className="text-neutral-200 font-semibold">{d.name}</span>
                    <div className="flex items-center gap-2 font-mono">
                      <span style={{ color: driverLabelColor(d.impact) }} className="font-bold">
                        {val}
                      </span>
                      <span 
                        className="text-[9px] uppercase font-bold px-1 py-0.25 rounded border"
                        style={{ 
                          color: impactColor(d.impact), 
                          borderColor: `color-mix(in oklch, ${impactColor(d.impact)} 30%, transparent)`,
                          backgroundColor: `color-mix(in oklch, ${impactColor(d.impact)} 10%, transparent)`
                        }}
                      >
                        {d.impact}
                      </span>
                    </div>
                  </div>
                  {/* Subtle bar representation */}
                  <div className="w-full h-1 bg-neutral-900 rounded-full overflow-hidden">
                    <div 
                      className={`h-full ${isPositive ? "bg-green-500" : isNegative ? "bg-red-500" : "bg-neutral-600"}`}
                      style={{ width: isPositive ? "100%" : isNegative ? "100%" : "30%" }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </motion.section>

        {/* Detailed Decision Trace */}
        <motion.section className="td-panel p-5 lg:col-span-2 flex flex-col gap-3" variants={itemVariants}>
          <div className="flex items-center justify-between border-b border-neutral-800/60 pb-3">
            <h2 className="text-[14px] font-medium flex items-center gap-2" style={{ color: "var(--td-ink-100)" }}>
              <Sliders className="text-teal-400" size={16} />
              Decision Engine Trace Details
            </h2>
            <span className="text-[10px] text-neutral-500 font-mono">
              Audit Logs
            </span>
          </div>

          <DecisionTrace decision={decision} />
        </motion.section>
      </div>


      {/* ========================================== */}
      {/* SECTION 3: OPTIONS SUGGESTIONS (Bottom)    */}
      {/* ========================================== */}

      {suggestion.options ? (
        <motion.section 
          className="td-panel p-5 border-l-4" 
          style={{ borderColor: suggestion.options.action === "buy" ? "var(--td-warning)" : "var(--td-line)" }}
          variants={itemVariants}
        >
          <div className="flex items-center justify-between border-b border-neutral-800/60 pb-3 mb-4">
            <h2 className="text-[14px] font-medium flex items-center gap-2" style={{ color: "var(--td-ink-100)" }}>
              <Zap className="text-yellow-400 animate-pulse" size={16} strokeWidth={2.5} />
              Suggested Options Strategy Option (Defined-Risk Hedge)
            </h2>
            <span className={`text-[10px] font-bold px-2 py-0.5 rounded font-mono uppercase ${suggestion.options.action === "buy" ? "bg-yellow-500/10 text-yellow-400 border border-yellow-500/20" : "bg-neutral-900 text-neutral-500"}`}>
              {suggestion.options.action === "buy" ? "Options Alert" : "No Option Edge"}
            </span>
          </div>

          {suggestion.options.action === "buy" ? (
            <div className="grid gap-4 lg:grid-cols-3">
              <div className="lg:col-span-2 flex flex-col gap-4">
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  <Stat label="Strategy Name" value={suggestion.options.structure || "—"} emphasize />
                  <Stat label="Option Expiry" value={suggestion.options.expiry || "—"} emphasize />
                  <Stat label="DTE (Days to Expiry)" value={suggestion.options.dte ? `${suggestion.options.dte} days` : "—"} emphasize />
                  <Stat label="Long strike" value={fmtUsd(suggestion.options.long_strike)} emphasize />
                  <Stat 
                    label="Short strike" 
                    value={suggestion.options.short_strike != null ? fmtUsd(suggestion.options.short_strike) : "—"} 
                    emphasize 
                  />
                  <Stat 
                    label="Net Debit / Share" 
                    value={suggestion.options.debit_per_share != null ? `$${fmt(suggestion.options.debit_per_share, 2)}` : "—"} 
                    emphasize 
                  />
                </div>

                <div className="grid grid-cols-2 gap-3 border-t border-dashed border-neutral-800/80 pt-4">
                  <Stat label="Max Loss (1 Contract)" value={fmtUsd(suggestion.options.max_loss_1_contract)} />
                  <Stat label="Long Strike Delta" value={suggestion.options.long_delta != null ? fmt(suggestion.options.long_delta, 2) : "—"} />
                </div>
              </div>

              {/* Sizing & comparison */}
              <div className="p-4 rounded-lg bg-neutral-900/35 border border-neutral-800/80 flex flex-col justify-between">
                <div>
                  <h3 className="text-[12px] font-semibold font-mono uppercase text-neutral-300 border-b border-neutral-800 pb-2 mb-3">
                    Option Capital Sizing
                  </h3>
                  
                  <div className="flex flex-col gap-2.5">
                    <div className="flex justify-between items-center text-[12.5px]">
                      <span className="text-neutral-400">Total Risk Budget</span>
                      <span className="font-mono font-semibold text-white">{fmtUsd(suggestion.options.budget)}</span>
                    </div>
                    <div className="flex justify-between items-center text-[12.5px]">
                      <span className="text-neutral-400">Max Risk per Contract</span>
                      <span className="font-mono text-neutral-200">{fmtUsd(suggestion.options.max_loss_1_contract)}</span>
                    </div>
                    <div className="flex justify-between items-center border-t border-neutral-800 pt-2.5 mt-1 text-[13.5px]">
                      <span className="text-white font-semibold">Suggested Contracts</span>
                      <span className="font-mono text-green-400 font-bold text-[16px]">
                        {suggestion.options.budget && suggestion.options.max_loss_1_contract
                          ? Math.max(0, Math.floor(suggestion.options.budget / suggestion.options.max_loss_1_contract))
                          : "—"}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="mt-4 pt-4 border-t border-neutral-800/80 text-[11px] text-neutral-400 leading-normal">
                  <span className="font-semibold block text-neutral-300 mb-1">Spread risk math</span>
                  Defined-risk spreads cap absolute downside at the net debit paid when IV is structurally cheap vs the path context.
                </div>
              </div>
            </div>
          ) : (
            <div className="p-4 rounded bg-neutral-900/20 border border-neutral-900 text-center">
              <p className="text-[13px] text-neutral-400 italic">
                {suggestion.options.reason || "No suitable option chain structures found for the current volatility regime."}
              </p>
            </div>
          )}
        </motion.section>
      ) : null}

      <motion.div variants={itemVariants} className="mt-2">
        <ModelFlow />
      </motion.div>
    </motion.div>
  );
}
