"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import type { ApiEnvelope, GammaResponse, LivePlanResponse } from "@/lib/types";
import {
  formatNum,
  formatPct,
  formatPctPoints,
  formatPctPointsUnsigned,
} from "@/lib/format";
import { ActionChip, actionStyle } from "@/components/ui/ActionChip";
import { PageHeader } from "@/components/shell/PageHeader";
import { GammaScene } from "@/components/gamma/GammaScene";
import { analyzeHref, liveHref, optionsHref } from "@/lib/routes";

function Stat({ label, value, emphasize }: { label: string; value: React.ReactNode; emphasize?: boolean }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-wider" style={{ color: "var(--td-ink-500)" }}>
        {label}
      </span>
      <span
        className={`tabular ${emphasize ? "text-[15px] font-medium" : "text-[13px]"}`}
        style={{ color: emphasize ? "var(--td-ink-100)" : "var(--td-ink-300)" }}
      >
        {value}
      </span>
    </div>
  );
}

function RegimeChip({ regime }: { regime: string }) {
  const isPin = regime === "positive_gex_pin";
  const isAmplify = regime === "negative_gex_amplify";
  const color = isPin ? "var(--td-brand)" : isAmplify ? "var(--td-action-avoid)" : "var(--td-action-wait)";
  const bg = `color-mix(in oklch, ${color} 18%, transparent)`;
  const label = isPin ? "PIN" : isAmplify ? "AMPLIFY" : "FLAT";
  return (
    <span
      className="td-action-chip td-action-chip--md"
      style={{ color, background: bg, border: `1px solid ${color}` }}
    >
      {label}
    </span>
  );
}

function SqueezeChip({ label }: { label: string | undefined }) {
  const style =
    label === "bullish_squeeze"
      ? actionStyle("BUY NOW")
      : label === "bearish_squeeze"
        ? actionStyle("AVOID")
        : actionStyle("WAIT");
  const text =
    label === "bullish_squeeze"
      ? "BULL SQUEEZE"
      : label === "bearish_squeeze"
        ? "BEAR SQUEEZE"
        : "NEUTRAL";
  return (
    <span
      className="td-action-chip td-action-chip--md"
      style={{ color: style.color, background: style.soft, border: `1px solid ${style.color}` }}
    >
      {text}
    </span>
  );
}

function SqueezeGauge({ score }: { score: number | undefined }) {
  if (score == null) return <span className="tabular">—</span>;
  const val = Math.max(-100, Math.min(100, score));
  const pos = (val + 100) / 2;
  const markerColor =
    val >= 20 ? "var(--td-action-buy-now)" : val <= -20 ? "var(--td-action-avoid)" : "var(--td-ink-100)";

  return (
    <div className="flex flex-col gap-2" style={{ minWidth: 220 }}>
      <div className="relative h-3 w-full">
        <div className="absolute inset-0 flex">
          <div className="h-full" style={{ width: "40%", background: "color-mix(in oklch, var(--td-action-avoid) 28%, transparent)" }} />
          <div className="h-full" style={{ width: "20%", background: "var(--td-surface-soft)" }} />
          <div className="h-full" style={{ width: "40%", background: "color-mix(in oklch, var(--td-brand) 28%, transparent)" }} />
        </div>
        <div className="absolute inset-y-0" style={{ left: "50%", width: 1, background: "var(--td-hairline)" }} />
        <div
          className="absolute"
          style={{ left: `calc(${pos}% - 1px)`, top: -3, width: 2, height: 18, background: markerColor }}
        />
      </div>
      <div className="flex justify-between text-[9px] tabular" style={{ color: "var(--td-ink-500)" }}>
        <span>BEAR −100</span>
        <span>−20</span>
        <span>0</span>
        <span>+20</span>
        <span>+100 BULL</span>
      </div>
      <div className="tabular text-[12px]" style={{ color: markerColor }}>
        {val > 0 ? "+" : ""}
        {formatNum(val, 1)}
      </div>
    </div>
  );
}

function useVerdict(gamma: GammaResponse | null, live: LivePlanResponse | null) {
  return useMemo(() => {
    const modelAction = live?.model?.action_hint ?? "—";
    const m = modelAction.toUpperCase();
    const isAggressive = /BUY NOW|BUY BREAKOUT|enter/i.test(m);
    const isWait = /BREAKOUT WATCH|PULLBACK ZONE|WAIT/i.test(m);
    const isAvoid = /AVOID|FLATTEN|HALT|stand|skip/i.test(m) && !isAggressive && !isWait;
    const hasModel = live?.model?.ok === true;

    const gexSign = gamma?.gex_sign ?? 0;
    const regime = gamma?.regime ?? "flat";
    const squeezeLabel = gamma?.squeeze_label ?? "neutral";
    const squeezeScore = gamma?.squeeze_score ?? 0;

    let consensus = "WAIT";
    let note = "No model signal. Use Gamma as a standalone read or run Analyze first.";

    if (hasModel) {
      if (isAggressive) {
        if (gexSign < 0) {
          consensus = "BUY NOW";
          note = "Gamma is short. Breakouts will accelerate. Follow the model size.";
        } else if (gexSign > 0) {
          consensus = "BREAKOUT WATCH";
          note = "Gamma is long. Expect chop at the call wall. Wait for a wall break or size down.";
        } else {
          consensus = "BUY NOW";
          note = "Gamma is flat. No hedging headwind. Follow the model.";
        }
      } else if (isWait) {
        if (gexSign < 0) {
          consensus = "BREAKOUT WATCH";
          note = "Gamma is short. A trigger through the call wall can run fast.";
        } else if (gexSign > 0) {
          consensus = "WAIT";
          note = "Gamma is long. Range-bound until the flip strikes break.";
        } else {
          consensus = "WAIT";
          note = "Gamma is flat. Follow the model trigger.";
        }
      } else if (isAvoid) {
        if (gexSign < 0) {
          consensus = "AVOID";
          note = "Gamma is short. Downside can accelerate. Stand aside.";
        } else if (gexSign > 0) {
          consensus = "AVOID";
          note = "Gamma is long but model says avoid. No trend edge; wait.";
        } else {
          consensus = "WAIT";
          note = "Gamma is flat. Follow the model trigger.";
        }
      } else if (gexSign === 0) {
        consensus = "WAIT";
        note = "Gamma is flat. Follow the model trigger.";
      } else {
        consensus = gexSign < 0 ? "BREAKOUT WATCH" : "WAIT";
        note = "Model signal unclear. Gamma points to volatility.";
      }
    } else if (gamma) {
      if (squeezeLabel === "bullish_squeeze") {
        consensus = "BREAKOUT WATCH";
        note = `Gamma squeeze score +${formatNum(squeezeScore, 1)}. Bullish breakout risk if spot reclaims the call wall.`;
      } else if (squeezeLabel === "bearish_squeeze") {
        consensus = "AVOID";
        note = `Gamma squeeze score ${formatNum(squeezeScore, 1)}. Bearish cascade risk if support breaks.`;
      } else {
        consensus = "WAIT";
        note = "Gamma is neutral. No directional squeeze edge.";
      }
    }

    const entry = live?.model?.entry;
    const emLow = gamma?.expected_move_low;
    const emHigh = gamma?.expected_move_high;
    if (entry != null && emLow != null && emHigh != null) {
      if (entry >= emLow && entry <= emHigh) {
        note += " Entry inside expected move — gamma fits.";
      } else {
        note += " Entry outside expected move — lower probability.";
      }
    }

    const spot = gamma?.spot;
    const callWall = gamma?.call_wall;
    const putWall = gamma?.put_wall;
    if (spot != null && callWall != null && Math.abs((spot - callWall) / callWall) <= 0.01) {
      note += " Price at call wall — resistance risk.";
    }
    if (spot != null && putWall != null && Math.abs((spot - putWall) / putWall) <= 0.01) {
      note += " Price at put wall — support risk.";
    }

    if (gamma?.squeeze_label) {
      note += ` Squeeze: ${gamma.squeeze_label.replace(/_/g, " ")} (${formatNum(gamma.squeeze_score, 1)}).`;
    }

    return { modelAction, gexSign, regime, consensus, note, squeezeLabel, squeezeScore };
  }, [gamma, live]);
}

function buildNotes(gamma: GammaResponse): string[] {
  const notes: string[] = [];
  if (gamma.squeeze_label != null) {
    const s = gamma.squeeze_label.replace(/_/g, " ").toUpperCase();
    notes.push(`Squeeze read: ${s} (${formatNum(gamma.squeeze_score, 1)}).`);
  }
  if (gamma.call_wall != null) {
    const d = gamma.dist_call_wall_pct;
    if (d != null && d > 0) {
      notes.push(`Call wall at ${formatNum(gamma.call_wall)} is ${formatPctPoints(d)} above spot — reclaim to squeeze.`);
    } else {
      notes.push(`Call wall at ${formatNum(gamma.call_wall)} is near or inside spot.`);
    }
  }
  if (gamma.put_wall != null) {
    const d = gamma.dist_put_wall_pct;
    if (d != null && d < 0) {
      notes.push(`Put wall at ${formatNum(gamma.put_wall)} is ${formatPctPoints(d)} below spot — lose to open downside.`);
    } else {
      notes.push(`Put wall at ${formatNum(gamma.put_wall)} is near or inside spot.`);
    }
  }
  if (gamma.expected_move_pct != null) {
    notes.push(
      `Expected move ±${formatPctPointsUnsigned(gamma.expected_move_pct)} (${formatNum(gamma.expected_move_low)} - ${formatNum(gamma.expected_move_high)}).`,
    );
  }
  if (gamma.max_pain != null) {
    notes.push(`Max pain ${formatNum(gamma.max_pain)} for nearest expiry.`);
  }
  if (gamma.approx_flip_strike != null) {
    notes.push(`Flip strike at ${formatNum(gamma.approx_flip_strike)} — regime changes there.`);
  }
  if (gamma.otm_call_oi > 0) {
    notes.push(`OTM call OI ${formatNum(gamma.otm_call_oi, 0)} — watch for participation / squeeze fuel.`);
  }
  if ((gamma.otm_put_oi ?? 0) > 0) {
    notes.push(`OTM put OI ${formatNum(gamma.otm_put_oi, 0)} — downside protection / bearish fuel.`);
  }
  return notes;
}

export function GammaExposureDesk() {
  const searchParams = useSearchParams();
  const qSymbol = searchParams.get("symbol")?.toUpperCase() ?? "";
  const [symbol, setSymbol] = useState(qSymbol || "APLD");
  const [spotSource, setSpotSource] = useState<"auto" | "lse" | "yfinance">("auto");
  const [source, setSource] = useState<"oi" | "lse">("oi");
  const [maxExpiries, setMaxExpiries] = useState<number | "">(4);
  const [maxDte, setMaxDte] = useState<number | "">(45);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gamma, setGamma] = useState<GammaResponse | null>(null);
  const [live, setLive] = useState<LivePlanResponse | null>(null);
  const [liveError, setLiveError] = useState<string | null>(null);

  useEffect(() => {
    if (qSymbol) setSymbol(qSymbol);
  }, [qSymbol]);

  const run = useCallback(
    async (symOverride?: string) => {
      const sym = (symOverride ?? symbol).trim().toUpperCase();
      if (!sym) return;
      setSymbol(sym);
      setLoading(true);
      setError(null);
      setLiveError(null);

      const gammaController = new AbortController();
      const liveController = new AbortController();
      const gammaTimer = setTimeout(() => gammaController.abort(), 90_000);
      const liveTimer = setTimeout(() => liveController.abort(), 120_000);

      try {
        const [gammaRes, liveRes] = await Promise.allSettled([
          fetch("/api/gamma", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              symbol: sym,
              spotSource,
              source,
              maxExpiries: maxExpiries === "" ? undefined : maxExpiries,
              maxDte: maxDte === "" ? undefined : maxDte,
            }),
            signal: gammaController.signal,
          }),
          fetch("/api/live-plan", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ symbol: sym, account: 1000 }),
            signal: liveController.signal,
          }),
        ]);

        clearTimeout(gammaTimer);
        clearTimeout(liveTimer);

        if (gammaRes.status !== "fulfilled") {
          throw new Error("Gamma request failed");
        }
        const gammaJson = (await gammaRes.value.json()) as ApiEnvelope<GammaResponse>;
        if (!gammaRes.value.ok || gammaJson.ok === false || !gammaJson.data) {
          throw new Error(gammaJson.error ?? `gamma failed (${gammaRes.value.status})`);
        }
        setGamma(gammaJson.data);

        if (liveRes.status === "fulfilled") {
          const liveJson = (await liveRes.value.json()) as ApiEnvelope<LivePlanResponse>;
          if (liveRes.value.ok && liveJson.ok && liveJson.data) {
            setLive(liveJson.data);
          } else {
            setLiveError(liveJson.error ?? "live plan unavailable");
          }
        } else {
          setLiveError(liveRes.reason instanceof Error ? liveRes.reason.message : String(liveRes.reason));
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "gamma failed");
      } finally {
        setLoading(false);
      }
    },
    [symbol, spotSource, source, maxExpiries, maxDte],
  );

  useEffect(() => {
    if (!qSymbol) return;
    void run(qSymbol);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qSymbol]);

  const verdict = useVerdict(gamma, live);
  const notes = useMemo(() => (gamma ? buildNotes(gamma) : []), [gamma]);

  return (
    <div className="td-page">
      <PageHeader
        title="Gamma"
        description="Dealer gamma exposure by strike. Use as a confirmation overlay for the model verdict."
        meta={
          gamma ? (
            <span
              className="tabular"
              style={{
                fontFamily: "var(--td-font-mono)",
                color: "var(--td-ink-500)",
                fontSize: "var(--td-text-caption)",
              }}
            >
              {symbol} · {new Date(gamma.asof_utc).toLocaleString()}
            </span>
          ) : null
        }
        actions={
          symbol ? (
            <div className="flex flex-wrap gap-2">
              <Link href={analyzeHref({ symbol })} className="td-btn td-btn-ghost no-underline">
                Analyze
              </Link>
              <Link href={liveHref(symbol)} className="td-btn td-btn-ghost no-underline">
                Live
              </Link>
              <Link href={optionsHref(symbol)} className="td-btn td-btn-ghost no-underline">
                Options
              </Link>
            </div>
          ) : null
        }
      />

      <section className="td-toolbar">
        <div className="td-toolbar__row">
          <label className="td-field td-field--grow">
            <span className="td-label">Symbol</span>
            <input
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              className="td-input"
              style={{ fontFamily: "var(--td-font-mono)" }}
            />
          </label>
          <label className="td-field">
            <span className="td-label">Spot source</span>
            <select
              value={spotSource}
              onChange={(e) => setSpotSource(e.target.value as typeof spotSource)}
              className="td-input"
            >
              <option value="auto">Auto (LSE → yfinance)</option>
              <option value="lse">LSE</option>
              <option value="yfinance">yfinance</option>
            </select>
          </label>
          <label className="td-field">
            <span className="td-label">Gamma source</span>
            <select
              value={source}
              onChange={(e) => setSource(e.target.value as typeof source)}
              className="td-input"
            >
              <option value="oi">OI (yfinance)</option>
              <option value="lse">LSE volume</option>
            </select>
          </label>
          <label className="td-field td-field--risk">
            <span className="td-label">Max expiries</span>
            <input
              type="number"
              min={1}
              value={maxExpiries}
              onChange={(e) => setMaxExpiries(e.target.value === "" ? "" : Number(e.target.value))}
              className="td-input"
              style={{ fontFamily: "var(--td-font-mono)" }}
            />
          </label>
          <label className="td-field td-field--risk">
            <span className="td-label">Max DTE</span>
            <input
              type="number"
              min={1}
              value={maxDte}
              onChange={(e) => setMaxDte(e.target.value === "" ? "" : Number(e.target.value))}
              className="td-input"
              style={{ fontFamily: "var(--td-font-mono)" }}
            />
          </label>
          <button
            type="button"
            onClick={() => void run()}
            disabled={loading || !symbol.trim()}
            className="td-btn td-btn-primary"
          >
            {loading ? "Loading…" : "Run gamma"}
          </button>
        </div>
        <p className="text-[11px]" style={{ color: "var(--td-ink-500)" }}>
          Spot prefers LSE candles; options chain from {source === "lse" ? "LSE volume/premium" : "yfinance open interest"}. Dealer GEX = -Γ·weight·100·S²·0.01.
        </p>
      </section>

      {error ? (
        <div className="td-alert td-alert--error" role="alert">
          {error}
        </div>
      ) : null}
      {liveError ? (
        <div className="td-alert" role="alert" style={{ color: "var(--td-ink-500)" }}>
          Model signal unavailable: {liveError}
        </div>
      ) : null}

      {!gamma && !loading && !error ? (
        <section className="td-panel p-5">
          <p
            className="text-[15px] font-medium"
            style={{ color: "var(--td-ink-100)", fontFamily: "var(--td-font-display)" }}
          >
            No gamma snapshot yet
          </p>
          <ol className="mt-2 flex flex-col gap-1 text-[13px]" style={{ color: "var(--td-ink-300)" }}>
            <li>1. Enter a symbol (start with APLD or IONQ)</li>
            <li>2. Run gamma → read regime, walls, and squeeze</li>
            <li>3. Compare the gamma view with the model signal</li>
          </ol>
        </section>
      ) : null}

      <AnimatePresence mode="wait">
        {gamma ? (
          <motion.div
            key="gamma"
            className="flex flex-col gap-4"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.45, ease: "easeOut" }}
          >
          {/* Verdict comparison */}
          <section
            className="td-panel p-4"
            style={{ borderLeft: `3px solid ${actionStyle(verdict.consensus).color}` }}
          >
            <div className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span className="td-eyebrow">Model vs Gamma</span>
                <ActionChip action={verdict.consensus} size="lg" />
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2" style={{ borderColor: "var(--td-hairline)" }}>
                <div className="flex flex-col gap-1">
                  <span className="td-label">Model</span>
                  <div className="flex flex-wrap items-center gap-2">
                    <ActionChip action={verdict.modelAction} size="sm" />
                    <span
                      className="text-[12px] tabular"
                      style={{ color: "var(--td-ink-500)", fontFamily: "var(--td-font-mono)" }}
                    >
                      {live?.model?.model ?? live?.model?.model ?? "—"} · {live?.model?.confidence != null ? formatPct(live.model.confidence, 0) : "—"}
                    </span>
                  </div>
                </div>
                <div className="flex flex-col gap-1">
                  <span className="td-label">Gamma</span>
                  <div className="flex flex-wrap items-center gap-2">
                    <RegimeChip regime={verdict.regime} />
                    <span
                      className="text-[12px] tabular"
                      style={{ color: "var(--td-ink-500)", fontFamily: "var(--td-font-mono)" }}
                    >
                      {formatNum(gamma.net_dealer_gex, 0)} GEX
                    </span>
                  </div>
                </div>
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="flex flex-col gap-1">
                  <span className="td-label">Squeeze</span>
                  <div className="flex flex-wrap items-start gap-2">
                    <SqueezeChip label={verdict.squeezeLabel} />
                    <SqueezeGauge score={verdict.squeezeScore} />
                  </div>
                </div>
                <div className="flex flex-col gap-1">
                  <span className="td-label">Source</span>
                  <span
                    className="text-[12px] tabular"
                    style={{ color: "var(--td-ink-500)", fontFamily: "var(--td-font-mono)" }}
                  >
                    {gamma.weight === "volume_today" ? "LSE volume" : "yfinance OI"} · {gamma.n_contracts} contracts
                  </span>
                </div>
              </div>
              <p className="text-[13px] leading-snug" style={{ color: "var(--td-ink-300)" }}>
                {verdict.note}
              </p>
            </div>
          </section>

          <div className="grid gap-4 lg:grid-cols-[1.25fr_0.75fr]">
            <section className="td-panel p-4">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <span className="td-eyebrow">Gamma by strike</span>
                <span className="text-[11px] tabular" style={{ color: "var(--td-ink-500)" }}>
                  {gamma.symbol} {formatNum(gamma.spot)} · {gamma.expiries_used.length} expiries · {gamma.n_contracts} contracts
                </span>
              </div>
              <GammaScene data={gamma} />
              <div className="mt-2 flex flex-wrap gap-4 text-[11px]" style={{ color: "var(--td-ink-500)" }}>
                <span className="inline-flex items-center gap-1">
                  <span className="inline-block h-2 w-3" style={{ background: "var(--td-brand)" }} />
                  Positive net GEX
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="inline-block h-2 w-3" style={{ background: "var(--td-action-avoid)" }} />
                  Negative net GEX
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="inline-block h-2 w-3" style={{ background: "var(--td-ink-100)" }} />
                  Spot
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="inline-block h-2 w-3" style={{ background: "var(--td-brand-soft)", opacity: 0.6 }} />
                  Expected move
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="inline-block h-2 w-3" style={{ background: "var(--td-action-buy-now)" }} />
                  Call wall
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="inline-block h-2 w-3" style={{ background: "var(--td-action-avoid)" }} />
                  Put wall
                </span>
              </div>
            </section>

            <section className="flex flex-col gap-4">
              <div className="td-panel p-4">
                <span className="td-eyebrow">Gamma summary</span>
                <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
                  <Stat label="Spot" value={`${formatNum(gamma.spot)} (${gamma.spot_source})`} emphasize />
                  <Stat label="Regime" value={<RegimeChip regime={gamma.regime} />} emphasize />
                  <Stat label="Squeeze" value={<SqueezeChip label={gamma.squeeze_label} />} emphasize />
                  <Stat label="Net dealer GEX" value={formatNum(gamma.net_dealer_gex, 0)} />
                  <Stat label="Near-spot GEX" value={formatNum(gamma.near_spot_dealer_gex, 0)} />
                  <Stat label="Squeeze score" value={formatNum(gamma.squeeze_score, 1)} />
                  <Stat label="Call wall" value={gamma.call_wall != null ? formatNum(gamma.call_wall) : "—"} />
                  <Stat label="Put wall" value={gamma.put_wall != null ? formatNum(gamma.put_wall) : "—"} />
                  <Stat
                    label="Expected move"
                    value={gamma.expected_move_pct != null ? `±${formatPctPointsUnsigned(gamma.expected_move_pct)}` : "—"}
                  />
                  <Stat label="Max pain" value={gamma.max_pain != null ? formatNum(gamma.max_pain) : "—"} />
                  <Stat label="Flip" value={gamma.approx_flip_strike != null ? formatNum(gamma.approx_flip_strike) : "—"} />
                  <Stat label="OTM call vol" value={formatNum(gamma.otm_call_volume, 0)} />
                  <Stat label="OTM call OI" value={formatNum(gamma.otm_call_oi, 0)} />
                  <Stat label="OTM put vol" value={formatNum(gamma.otm_put_volume, 0)} />
                  <Stat label="OTM put OI" value={formatNum(gamma.otm_put_oi, 0)} />
                  <Stat label="Asof" value={new Date(gamma.asof_utc).toLocaleString()} />
                </div>
              </div>

              <div className="td-panel p-4">
                <span className="td-eyebrow">How to read gamma</span>
                <ul className="mt-2 flex flex-col gap-1.5 text-[13px]" style={{ color: "var(--td-ink-300)" }}>
                  {notes.map((n, i) => (
                    <li key={i} className="leading-snug">
                      {n}
                    </li>
                  ))}
                  {notes.length === 0 ? <li className="leading-snug">No notes.</li> : null}
                </ul>
              </div>
            </section>
          </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
