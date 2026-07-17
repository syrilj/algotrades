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
import { Chip } from "@/components/ui/Chip";
import { colorVarFor } from "@/lib/actionColors";
import { Stat } from "@/components/ui/Stat";
import {
  gammaDeskPresentation,
  gammaFreshness,
  gammaMethodology,
} from "@/lib/executionState";

function RegimeChip({ regime }: { regime: string }) {
  const isPin = regime === "positive_gex_pin";
  const isAmplify = regime === "negative_gex_amplify";
  const label = isPin ? "PIN" : isAmplify ? "AMPLIFY" : "FLAT";
  return <Chip label={label} colorVar={colorVarFor("regime", regime)} />;
}

function SqueezeChip({ label }: { label: GammaResponse["squeeze_label"] }) {
  const text = label === "bullish_squeeze" ? "UPSIDE SQUEEZE" : label === "bearish_squeeze" ? "DOWNSIDE SQUEEZE" : "NO SQUEEZE";
  return <Chip label={text} colorVar={colorVarFor("regime", label)} />;
}

const SQUEEZE_DRIVER_COPY: Record<string, string> = {
  regime_score: "Negative gamma near spot can amplify a move.",
  call_prox_score: "Price is close enough to the call wall for an upside break to matter.",
  put_prox_score: "Price is close enough to the put wall for a downside break to matter.",
  call_conc_score: "More call positioning sits above spot than put positioning below it.",
  put_conc_score: "More put positioning sits below spot than call positioning above it.",
  wall_asym_score: "One wall is materially larger than the opposing wall.",
  em_score: "The relevant wall is inside the expected move for the selected expiries.",
  flip_score: "Spot is close to the gamma-flip level, so the regime can change quickly.",
};

function SqueezeSummary({ gamma }: { gamma: GammaResponse }) {
  const score = gamma.squeeze_score ?? 0;
  const label = gamma.squeeze_label ?? "neutral";
  const direction = label === "bullish_squeeze" ? "Upside acceleration is possible if price clears the call wall." : label === "bearish_squeeze" ? "Downside acceleration is possible if price loses the put wall." : "The selected options book does not show a directional squeeze setup.";
  const drivers = Object.entries(gamma.squeeze_components ?? {})
    .filter(([, value]) => Number.isFinite(value) && Math.abs(value) >= 0.25)
    .sort(([, a], [, b]) => Math.abs(b) - Math.abs(a))
    .slice(0, 3);
  const color = label === "bullish_squeeze" ? "var(--td-action-buy-now)" : label === "bearish_squeeze" ? "var(--td-action-avoid)" : "var(--td-ink-300)";

  return (
    <div className="td-panel p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <span className="td-eyebrow">Squeeze read</span>
          <div className="mt-2"><SqueezeChip label={label} /></div>
        </div>
        <div className="text-right">
          <div className="td-label">Pressure score</div>
          <div className="tabular text-[22px] font-semibold" style={{ color, fontFamily: "var(--td-font-mono)" }}>
            {score > 0 ? "+" : ""}{formatNum(score, 1)}
          </div>
        </div>
      </div>
      <p className="mt-3 text-[13px] leading-snug" style={{ color: "var(--td-ink-300)" }}>{direction}</p>
      <p className="mt-1 text-[11px] leading-snug" style={{ color: "var(--td-ink-500)" }}>
        This is an options-structure heuristic, not an entry signal. It updates with the selected expiry dates.
      </p>
      {drivers.length > 0 ? (
        <div className="mt-3 border-t pt-3" style={{ borderColor: "var(--td-hairline)" }}>
          <div className="td-label mb-2">Why it reads this way</div>
          <ul className="flex flex-col gap-1.5 text-[12px] leading-snug" style={{ color: "var(--td-ink-300)" }}>
            {drivers.map(([key]) => <li key={key}>{SQUEEZE_DRIVER_COPY[key] ?? key.replace(/_/g, " ")}</li>)}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function wallDistanceCopy(distance: number | null | undefined, side: "call" | "put"): string {
  if (distance == null) return "distance unavailable";
  if (Math.abs(distance) <= 0.25) return "at spot";
  if (side === "call") {
    return distance > 0 ? `${formatPctPointsUnsigned(distance)} overhead` : `${formatPctPointsUnsigned(distance)} reclaimed`;
  }
  return distance < 0 ? `${formatPctPointsUnsigned(distance)} below spot` : `${formatPctPointsUnsigned(distance)} broken`;
}

function ReadoutTile({
  label,
  value,
  detail,
  color,
}: {
  label: string;
  value: React.ReactNode;
  detail?: React.ReactNode;
  color?: string;
}) {
  return (
    <div className="border p-3" style={{ borderColor: "var(--td-hairline)", background: "var(--td-canvas)" }}>
      <div className="td-label">{label}</div>
      <div
        className="mt-1 tabular text-[15px] font-semibold"
        style={{ color: color ?? "var(--td-ink-100)", fontFamily: "var(--td-font-mono)" }}
      >
        {value}
      </div>
      {detail ? (
        <div className="mt-1 text-[11px] leading-snug" style={{ color: "var(--td-ink-500)" }}>
          {detail}
        </div>
      ) : null}
    </div>
  );
}

function WallCard({
  title,
  value,
  distance,
  gex,
  side,
}: {
  title: string;
  value: number | null | undefined;
  distance: number | null | undefined;
  gex: number | null | undefined;
  side: "call" | "put";
}) {
  const color = side === "call" ? "var(--td-action-buy-now)" : "var(--td-action-avoid)";
  const isLive = distance != null && Math.abs(distance) <= 1;
  return (
    <div
      className="border p-3"
      style={{
        borderColor: isLive ? color : "var(--td-hairline)",
        background: isLive ? `color-mix(in oklch, ${color} 9%, var(--td-canvas))` : "var(--td-canvas)",
      }}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="td-label">{title}</span>
        <span className="text-[10px] uppercase tracking-[1.4px]" style={{ color: isLive ? color : "var(--td-ink-500)" }}>
          {isLive ? "active" : "watch"}
        </span>
      </div>
      <div className="mt-2 tabular text-[20px] font-semibold leading-none" style={{ color, fontFamily: "var(--td-font-mono)" }}>
        {value != null ? formatNum(value) : "—"}
      </div>
      <div className="mt-2 flex items-center justify-between gap-3 text-[11px] tabular" style={{ color: "var(--td-ink-500)" }}>
        <span>{wallDistanceCopy(distance, side)}</span>
        <span>{gex != null ? `${formatNum(gex, 0)} GEX` : "GEX —"}</span>
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
    const isFlowProxy = gamma?.exposure_kind === "intraday_gamma_flow_proxy";
    const gammaSubject = isFlowProxy ? "Near-spot gamma flow" : "Near-spot dealer gamma";
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
        note = `Upside squeeze pressure is ${formatNum(squeezeScore, 1)}. Watch the call wall; the heuristic matters only if price actually clears it.`;
      } else if (squeezeLabel === "bearish_squeeze") {
        consensus = "AVOID";
        note = `Downside squeeze pressure is ${formatNum(squeezeScore, 1)}. Watch the put wall; the heuristic matters only if price actually loses it.`;
      } else {
        consensus = gexSign < 0 ? "BREAKOUT WATCH" : "WAIT";
        note = gexSign < 0
          ? `${gammaSubject} is negative. A level break can expand volatility.`
          : gexSign > 0
            ? `${gammaSubject} is positive. Expect more pinning around the strongest strikes.`
            : `${isFlowProxy ? "Gamma flow" : "Dealer gamma"} is balanced. Wait for a price-level break.`;
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

    return { modelAction, gexSign, regime, consensus, note, squeezeLabel, squeezeScore };
  }, [gamma, live]);
}

function buildNotes(gamma: GammaResponse): string[] {
  const notes: string[] = [];
  if (gamma.call_wall != null) {
    const d = gamma.dist_call_wall_pct;
    if (d != null && d > 0) {
      notes.push(`Call wall at ${formatNum(gamma.call_wall)} is ${formatPctPoints(d)} above spot — resistance until price clears it.`);
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
  if ((gamma.otm_call_oi ?? 0) > 0) {
    notes.push(`OTM call OI ${formatNum(gamma.otm_call_oi, 0)} — participation above spot.`);
  }
  if ((gamma.otm_put_oi ?? 0) > 0) {
    notes.push(`OTM put OI ${formatNum(gamma.otm_put_oi, 0)} — downside protection / bearish fuel.`);
  }
  return notes;
}


export function GammaExposureDesk({
  showHeader = true,
}: {
  showHeader?: boolean;
}) {
  const searchParams = useSearchParams();
  const qSymbol = searchParams.get("symbol")?.toUpperCase() ?? "";
  const qAccount = Number(searchParams.get("account") || "1000");
  const account = Number.isFinite(qAccount) && qAccount > 0 ? qAccount : 1000;
  const [symbol, setSymbol] = useState(qSymbol || "APLD");
  // Empty until first options chain returns real listed expiries — never invent calendar dates.
  const [selectedExpiry, setSelectedExpiry] = useState("all");
  const [listedExpiries, setListedExpiries] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gamma, setGamma] = useState<GammaResponse | null>(null);
  const [live, setLive] = useState<LivePlanResponse | null>(null);
  const [liveError, setLiveError] = useState<string | null>(null);

  useEffect(() => {
    if (qSymbol) setSymbol(qSymbol);
  }, [qSymbol]);

  const run = useCallback(
    async (symOverride?: string, opts?: { resetExpiry?: boolean; targetExpiry?: string }) => {
      const sym = (symOverride ?? symbol).trim().toUpperCase();
      if (!sym) return;
      const resetExpiry = opts?.resetExpiry === true || sym !== symbol;
      setSymbol(sym);
      setLoading(true);
      setError(null);
      setLiveError(null);

      let currentExp = selectedExpiry;
      if (opts?.targetExpiry !== undefined) {
        currentExp = opts.targetExpiry;
      }
      if (resetExpiry) {
        currentExp = "all";
        setSelectedExpiry("all");
        setListedExpiries([]);
      }

      const gammaController = new AbortController();
      const liveController = new AbortController();
      const gammaTimer = setTimeout(() => gammaController.abort(), 90_000);
      const liveTimer = setTimeout(() => liveController.abort(), 120_000);

      try {
        const body: Record<string, unknown> = { symbol: sym, source: "auto" };
        if (currentExp && currentExp !== "all") {
          body.expiryFrom = currentExp;
          body.expiryTo = currentExp;
        }

        const [gammaRes, liveRes] = await Promise.allSettled([
          fetch("/api/gamma", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
            signal: gammaController.signal,
          }),
          fetch("/api/live-plan", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ symbol: sym, account }),
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
        const data = gammaJson.data;
        setGamma(data);

        const listed = (data.available_expiries?.length
          ? data.available_expiries
          : data.expiries_used
        ).filter((d) => /^\d{4}-\d{2}-\d{2}$/.test(d));
        if (listed.length > 0) {
          setListedExpiries(listed);
        }

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
    [symbol, selectedExpiry, account],
  );

  useEffect(() => {
    void run(qSymbol || symbol, { resetExpiry: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qSymbol]);

  useEffect(() => {
    if (symbol) {
      void run(symbol, { resetExpiry: false });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedExpiry]);

  const verdict = useVerdict(gamma, live);
  const notes = useMemo(() => (gamma ? buildNotes(gamma) : []), [gamma]);
  const freshness = useMemo(
    () =>
      gamma
        ? gammaFreshness({
            options_asof: gamma.options_asof,
            asof_utc: gamma.asof_utc,
            exposure_kind: gamma.exposure_kind,
          })
        : null,
    [gamma],
  );
  const methodology = useMemo(() => gammaMethodology(gamma), [gamma]);
  // Analysis levels always render when a snapshot exists. Freshness only labels age.
  const deskView = useMemo(
    () =>
      gammaDeskPresentation(
        gamma
          ? {
              options_asof: gamma.options_asof,
              asof_utc: gamma.asof_utc,
              exposure_kind: gamma.exposure_kind,
            }
          : null,
      ),
    [gamma],
  );
  const showLevels = deskView.showLevels;

  const body = (
    <>
      {showHeader ? (
        <PageHeader
          title="Gamma"
          description="Gamma-derived levels from current option flow, with open-interest fallback when available."
          meta={
            gamma ? (
              <span
                className="tabular"
                style={{
                  fontFamily: "var(--td-font-mono)",
                  color: freshness?.isStale
                    ? "var(--td-action-avoid)"
                    : "var(--td-ink-500)",
                  fontSize: "var(--td-text-caption)",
                }}
              >
                {symbol} · options{" "}
                {freshness?.hasTimestamp
                  ? freshness.dataDate.toLocaleString()
                  : "timestamp unavailable"}
                {!freshness?.isCurrent ? " · not live" : ""}
              </span>
            ) : null
          }
          actions={
            symbol ? (
              <div className="flex flex-wrap gap-2">
                <Link
                  href={analyzeHref({ symbol })}
                  className="td-btn td-btn-ghost no-underline"
                >
                  Analyze
                </Link>
                <Link
                  href={liveHref(symbol, "ticket", account)}
                  className="td-btn td-btn-ghost no-underline"
                >
                  Ticket
                </Link>
                <Link
                  href={optionsHref(symbol, account)}
                  className="td-btn td-btn-ghost no-underline"
                >
                  Options
                </Link>
              </div>
            ) : null
          }
        />
      ) : null}

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
            <span className="td-label">Expiry Date</span>
            <select
              value={selectedExpiry}
              onChange={(e) => setSelectedExpiry(e.target.value)}
              className="td-input"
              style={{ fontFamily: "var(--td-font-mono)" }}
            >
              <option value="all">All Expirations</option>
              {listedExpiries.map((d) => (
                <option key={`expiry-${d}`} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={() => void run()}
            disabled={loading || !symbol.trim()}
            className="td-btn td-btn-primary"
          >
            {loading ? "Loading live feed…" : gamma ? "Refresh live gamma" : "Load live gamma feed"}
          </button>
        </div>
        <p className="text-[11px]" style={{ color: "var(--td-ink-500)" }}>
          Expiry bounds come from listed option dates for this symbol — not calendar guesses.
          Flow is preferred when price-consistent; otherwise open-interest walls. Aged snapshots stay visible with a banner; execution still requires a live feed.
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
      {deskView.banner ? (
        <div
          className="td-alert"
          role="status"
          style={{
            border: "1px solid var(--td-action-breakout-watch)",
            color: "var(--td-action-breakout-watch)",
            background: "color-mix(in oklch, var(--td-action-breakout-watch) 10%, transparent)",
          }}
        >
          {deskView.banner}
        </div>
      ) : null}

      {!gamma && !loading && !error ? (
        <section className="td-panel p-5">
          <p
            className="text-[15px] font-medium"
            style={{ color: "var(--td-ink-100)", fontFamily: "var(--td-font-display)" }}
          >
            No live gamma feed yet
          </p>
          <ol className="mt-2 flex flex-col gap-1 text-[13px]" style={{ color: "var(--td-ink-300)" }}>
            <li>1. Enter a symbol (or keep the default)</li>
            <li>2. Press <strong>Load live gamma feed</strong></li>
            <li>3. Read walls, squeeze, and the strike board — expiry dates come from the chain</li>
          </ol>
        </section>
      ) : null}

      <AnimatePresence mode="wait">
        {showLevels && gamma ? (
          <motion.div
            key="gamma"
            className="flex flex-col gap-4"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.45, ease: "easeOut" }}
          >
          {/* Command readout */}
          <section
            className="td-panel overflow-hidden"
            style={{ borderLeft: `3px solid ${actionStyle(verdict.consensus).color}` }}
          >
            <div className="grid gap-0 lg:grid-cols-[0.95fr_1.05fr]">
              <div className="flex flex-col justify-between gap-4 p-4" style={{ background: "var(--td-canvas)" }}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <span className="td-eyebrow">Gamma command read</span>
                    <div
                      className="mt-1 text-[28px] font-semibold leading-none tracking-[-0.02em]"
                      style={{ color: "var(--td-ink-100)", fontFamily: "var(--td-font-display)" }}
                    >
                      {gamma.symbol} {formatNum(gamma.spot)}
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <RegimeChip regime={verdict.regime} />
                      <SqueezeChip label={verdict.squeezeLabel} />
                    </div>
                  </div>
                  <ActionChip action={verdict.consensus} size="lg" />
                </div>

                <p className="max-w-2xl text-[13px] leading-snug" style={{ color: "var(--td-ink-300)" }}>
                  {verdict.note}
                </p>

                <div className="flex flex-wrap gap-x-5 gap-y-2 text-[11px] tabular" style={{ color: "var(--td-ink-500)" }}>
                  <span>
                    Model: {live?.model?.model ?? "—"} · {live?.model?.confidence != null ? formatPct(live.model.confidence, 0) : "—"}
                  </span>
                  <span>
                    {methodology.label} · {gamma.n_contracts} contracts
                  </span>
                </div>
              </div>

              <div className="grid gap-3 border-t p-4 lg:border-l lg:border-t-0" style={{ borderColor: "var(--td-hairline)" }}>
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  <ReadoutTile
                    label={gamma.exposure_kind === "intraday_gamma_flow_proxy" ? "Net gamma-flow proxy" : "Net dealer GEX estimate"}
                    value={formatNum(gamma.net_dealer_gex, 0)}
                    detail={gamma.gex_sign < 0 ? "Negative gamma: range can expand." : gamma.gex_sign > 0 ? "Positive gamma: pinning risk." : gamma.exposure_kind === "intraday_gamma_flow_proxy" ? "Balanced option flow." : "Flat dealer book."}
                    color={gamma.gex_sign < 0 ? "var(--td-action-avoid)" : gamma.gex_sign > 0 ? "var(--td-brand)" : "var(--td-ink-300)"}
                  />
                  <ReadoutTile
                    label="Near-spot GEX"
                    value={formatNum(gamma.near_spot_dealer_gex, 0)}
                    detail="Fuel closest to live price."
                    color={gamma.near_spot_dealer_gex < 0 ? "var(--td-action-avoid)" : "var(--td-brand)"}
                  />
                  <ReadoutTile
                    label="Expected move"
                    value={gamma.expected_move_pct != null ? `±${formatPctPointsUnsigned(gamma.expected_move_pct)}` : "—"}
                    detail={`${formatNum(gamma.expected_move_low)} - ${formatNum(gamma.expected_move_high)}`}
                  />
                  <ReadoutTile
                    label="Flip distance"
                    value={gamma.dist_flip_pct != null ? formatPctPoints(gamma.dist_flip_pct) : "—"}
                    detail={gamma.approx_flip_strike != null ? `Flip ${formatNum(gamma.approx_flip_strike)}` : "No flip strike."}
                    color={gamma.dist_flip_pct != null && Math.abs(gamma.dist_flip_pct) <= 3 ? "var(--td-action-breakout-watch)" : undefined}
                  />
                  <ReadoutTile
                    label="Squeeze"
                    value={verdict.squeezeLabel === "bullish_squeeze" ? "Upside" : verdict.squeezeLabel === "bearish_squeeze" ? "Downside" : "None"}
                    detail={`Pressure ${verdict.squeezeScore > 0 ? "+" : ""}${formatNum(verdict.squeezeScore, 1)}`}
                    color={verdict.squeezeLabel === "bullish_squeeze" ? "var(--td-action-buy-now)" : verdict.squeezeLabel === "bearish_squeeze" ? "var(--td-action-avoid)" : undefined}
                  />
                </div>
              </div>
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
              <p className="mt-2 text-[11px]" style={{ color: "var(--td-ink-500)" }}>
                Choose Net, Calls, or Puts, then limit the board to strikes around spot. Dashed lines mark spot and the relevant walls.
              </p>
            </section>

            <section className="flex flex-col gap-4">
              <div className="td-panel p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <span className="td-eyebrow">Wall board</span>
                  <span className="text-[10px] uppercase tracking-[1.4px]" style={{ color: "var(--td-ink-500)" }}>
                    spot-relative
                  </span>
                </div>
                <div className="grid gap-3">
                  <WallCard
                    title="Call wall"
                    value={gamma.call_wall}
                    distance={gamma.dist_call_wall_pct}
                    gex={gamma.call_wall_gex}
                    side="call"
                  />
                  <WallCard
                    title="Put wall"
                    value={gamma.put_wall}
                    distance={gamma.dist_put_wall_pct}
                    gex={gamma.put_wall_gex}
                    side="put"
                  />
                </div>
                <div className="mt-3 grid grid-cols-2 gap-3">
                  <ReadoutTile label="Max pain" value={gamma.max_pain != null ? formatNum(gamma.max_pain) : "—"} />
                  <ReadoutTile label="Flip strike" value={gamma.approx_flip_strike != null ? formatNum(gamma.approx_flip_strike) : "—"} />
                </div>
              </div>

              <SqueezeSummary gamma={gamma} />

              <div className="td-panel p-4">
                <span className="td-eyebrow">{gamma.exposure_kind === "intraday_gamma_flow_proxy" ? "Flow snapshot" : "Positioning estimate"}</span>
                <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-3">
                  <Stat label="Spot" value={`${formatNum(gamma.spot)} (${gamma.spot_source})`} emphasize />
                  <Stat label="Regime" value={<RegimeChip regime={gamma.regime} />} emphasize />
                  <Stat label="OTM call vol" value={formatNum(gamma.otm_call_volume, 0)} />
                  <Stat label="OTM call OI" value={formatNum(gamma.otm_call_oi, 0)} />
                  <Stat label="OTM put vol" value={formatNum(gamma.otm_put_volume, 0)} />
                  <Stat label="OTM put OI" value={formatNum(gamma.otm_put_oi, 0)} />
                  <Stat
                    label={
                      gamma.exposure_kind === "intraday_gamma_flow_proxy"
                        ? "Flow as-of"
                        : "Chain last trade"
                    }
                    value={
                      freshness?.hasChainTimestamp || freshness?.hasTimestamp
                        ? freshness.dataDate.toLocaleString()
                        : "—"
                    }
                  />
                  <Stat
                    label="Expiries in book"
                    value={
                      (gamma.expiries_used ?? [])
                        .filter((d) => /^\d{4}-\d{2}-\d{2}$/.test(d))
                        .slice(0, 4)
                        .join(" · ") || "—"
                    }
                  />
                </div>
                <p className="mt-3 text-[11px] leading-snug" style={{ color: "var(--td-ink-500)" }}>
                  {methodology.detail}
                  {gamma.exposure_kind !== "intraday_gamma_flow_proxy"
                    ? " Open-interest last-trade stamps are delayed by design; squeeze and walls still use this snapshot."
                    : ""}
                </p>
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
    </>
  );

  return showHeader ? <div className="td-page">{body}</div> : body;
}
