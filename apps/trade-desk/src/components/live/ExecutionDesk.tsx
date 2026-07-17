"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Crosshair,
  Loader2,
  Radar,
  Radio,
  RefreshCw,
  Search,
  ShieldCheck,
  TicketCheck,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Chip } from "@/components/ui/Chip";
import { Stat } from "@/components/ui/Stat";
import { colorVarFor } from "@/lib/actionColors";
import {
  analysisSetupLabel,
  buildPaperOrder,
  decisionPresentation,
  feedPresentation,
  gammaMethodology,
  riskModeLabel,
  ticketDisplayFromPlan,
} from "@/lib/executionState";
import { formatNum, formatPct, formatPctPoints, formatUsd } from "@/lib/format";
import { analyzeHref, gammaHref, liveHref, optionsHref, positionsHref, watchHref } from "@/lib/routes";
import type {
  ApiEnvelope,
  GammaResponse,
  LivePlanResponse,
  LiveScanResponse,
  LiveScanRow,
  OptionsPlanResponse,
  PaperPosition,
} from "@/lib/types";

type PaperOrder = NonNullable<ReturnType<typeof buildPaperOrder>>;

function cleanReason(reason: string): string {
  const labels: Record<string, string> = {
    market_data_stale_or_unavailable: "Waiting for fresh market data",
    calibration_artifact_missing: "Live probability calibration is unavailable",
    calibration_artifact_not_active: "Live probability calibration is inactive",
    calibration_gates_failed: "Live calibration has not passed its safety gates",
    setup_not_ready: "The entry setup is not ready",
    calibrated_probability_below_entry_threshold: "Confidence is below the entry threshold",
    portfolio_state_verified: "Portfolio equity, drawdown, and open positions are not verified",
    trusted_execution_feed: "Live market data is unavailable (need LSE or yfinance with a usable price)",
    fresh_market_data: "Market data is stale or unavailable",
    macro_data_complete: "Macro context is incomplete",
    model_probability_available: "Model probability is unavailable",
    active_calibration: "No active calibration has passed the safety gates",
    confidence_enter: "The confidence gate has not authorized an entry",
    risk_manager_enter: "The risk manager did not authorize an entry",
    price_sources_consistent: "Market price sources conflict",
    risk_within_hard_cap: "The executable risk budget failed its hard-cap check",
    concrete_order_sized: "A valid order could not be sized",
  };
  return labels[reason] ?? reason.replaceAll("_", " ");
}

function formatAsOf(value: string | null | undefined): string {
  if (!value) return "Unavailable";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "Unavailable";
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

function PaperExecution({
  order,
  plan,
  override = false,
}: {
  order: PaperOrder;
  plan: LivePlanResponse;
  override?: boolean;
}) {
  const [armed, setArmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [position, setPosition] = useState<PaperPosition | null>(null);

  async function logPaperOrder() {
    if (!armed) {
      setArmed(true);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/trade", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...order,
          riskPct: plan.ticket?.risk_pct,
          action: plan.ticket?.action,
          confidence: plan.confidence?.calibrated_probability,
          reason: override ? "Simulated trade override logged by user" : "Verified in the guided Execution workspace",
          override,
        }),
      });
      const json = (await response.json()) as ApiEnvelope<{ position: PaperPosition }>;
      if (!response.ok || !json.ok || !json.data?.position) {
        throw new Error(json.error ?? `Paper order failed (${response.status})`);
      }
      setPosition(json.data.position);
      setArmed(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Paper order failed");
    } finally {
      setBusy(false);
    }
  }

  if (position) {
    return (
      <div className="exec-order-confirmed" role="status">
        <CheckCircle2 aria-hidden="true" />
        <div>
          <strong>Paper position logged {override && "(Overridden)"}</strong>
          <span>{position.id}</span>
        </div>
        <Link href={positionsHref()} className="td-btn td-btn-ghost no-underline">
          View position
        </Link>
      </div>
    );
  }

  return (
    <div className="exec-paper-order">
      <div>
        <span className="td-eyebrow">PAPER EXECUTION {override && "(OVERRIDE ENABLED)"}</span>
        <strong>{armed ? "Confirm the simulated order" : "Test this plan safely"}</strong>
        <p>
          {armed
            ? `${order.side.toUpperCase()} ${order.shares} ${order.symbol} at ${formatUsd(order.entry)} with stop ${formatUsd(order.stop)}.`
            : "This records a paper position. It never sends an order to a broker."}
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        {armed ? (
          <button type="button" className="td-btn td-btn-ghost" onClick={() => setArmed(false)}>
            Cancel
          </button>
        ) : null}
        <button
          type="button"
          className="td-btn td-btn-primary"
          onClick={() => void logPaperOrder()}
          disabled={busy}
        >
          {busy ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : null}
          {busy ? "Logging…" : armed ? "Confirm paper order" : "Review paper order"}
        </button>
      </div>
      {error ? <p className="td-alert td-alert--error">{error}</p> : null}
    </div>
  );
}

export function ExecutionDesk() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const qSymbol = searchParams.get("symbol")?.trim().toUpperCase() ?? "";
  const qAccount = Number(searchParams.get("account") || "1000");

  const [symbol, setSymbol] = useState(qSymbol);
  const [account, setAccount] = useState(
    Number.isFinite(qAccount) && qAccount > 0 ? qAccount : 1000,
  );
  const [plan, setPlan] = useState<LivePlanResponse | null>(null);
  const [scan, setScan] = useState<LiveScanResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gammaFeed, setGammaFeed] = useState<GammaResponse | null>(null);
  const [gammaFeedError, setGammaFeedError] = useState<string | null>(null);
  const [gammaLoading, setGammaLoading] = useState(false);
  const [optionsFeed, setOptionsFeed] = useState<OptionsPlanResponse | null>(null);
  const [optionsFeedError, setOptionsFeedError] = useState<string | null>(null);
  const [optionsLoading, setOptionsLoading] = useState(false);
  const [showReadinessDetails, setShowReadinessDetails] = useState(false);
  const [showOverride, setShowOverride] = useState(false);
  const [overrideShares, setOverrideShares] = useState(1);
  const [overrideEntry, setOverrideEntry] = useState(0);
  const [overrideStop, setOverrideStop] = useState(0);
  const lastPlannedRef = useRef<string | null>(null);

  useEffect(() => {
    if (qSymbol) setSymbol(qSymbol);
  }, [qSymbol]);

  const runPlan = useCallback(
    async (override?: string) => {
      const sym = (override ?? symbol).trim().toUpperCase();
      if (!sym) return;
      setSymbol(sym);
      setLoading(true);
      setError(null);
      setPlan(null);
      setGammaFeed(null);
      setOptionsFeed(null);

      setShowReadinessDetails(false);
      setShowOverride(false);
      try {
        const response = await fetch("/api/live-plan", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            symbol: sym,
            account,
            peak: account,
            model: "auto",
          }),
        });
        const json = (await response.json()) as ApiEnvelope<LivePlanResponse>;
        if (!response.ok || !json.ok || !json.data) {
          throw new Error(json.error ?? `Live plan failed (${response.status})`);
        }
        setPlan(json.data);
        lastPlannedRef.current = `${sym}:${account}`;
        router.replace(liveHref(sym, "ticket", account), {
          scroll: false,
        });
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Live plan failed");
      } finally {
        setLoading(false);
      }
    },
    [account, router, symbol],
  );

  useEffect(() => {
    if (!qSymbol) return;
    if (lastPlannedRef.current === `${qSymbol}:${account}`) return;
    void runPlan(qSymbol);
    // Deep links should arrive with a ready decision.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qSymbol, account]);

  const runScan = useCallback(async () => {
    setScanning(true);
    setError(null);
    try {
      const response = await fetch("/api/live-plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scan: true, account, peak: account, noModel: true }),
      });
      const json = (await response.json()) as ApiEnvelope<LiveScanResponse>;
      if (!response.ok || !json.ok || !json.data) {
        throw new Error(json.error ?? `Market scan failed (${response.status})`);
      }
      setScan(json.data);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Market scan failed");
    } finally {
      setScanning(false);
    }
  }, [account]);

  const loadGammaFeed = useCallback(
    async (symOverride?: string) => {
      const sym = (symOverride ?? plan?.symbol ?? symbol).trim().toUpperCase();
      if (!sym) return;
      setGammaLoading(true);
      setGammaFeedError(null);
      try {
        const response = await fetch("/api/gamma", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ symbol: sym, source: "auto" }),
        });
        const json = (await response.json()) as ApiEnvelope<GammaResponse>;
        if (!response.ok || !json.ok || !json.data) {
          throw new Error(json.error ?? `Gamma feed failed (${response.status})`);
        }
        setGammaFeed(json.data);
      } catch (caught) {
        setGammaFeedError(caught instanceof Error ? caught.message : "Gamma feed failed");
      } finally {
        setGammaLoading(false);
      }
    },
    [plan?.symbol, symbol],
  );

  const loadOptionsFeed = useCallback(
    async (symOverride?: string) => {
      const sym = (symOverride ?? plan?.symbol ?? symbol).trim().toUpperCase();
      if (!sym) return;
      setOptionsLoading(true);
      setOptionsFeedError(null);
      try {
        const response = await fetch("/api/options-plan", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ symbol: sym, account, peak: account, risk_pct: 18 }),
        });
        const json = (await response.json()) as ApiEnvelope<OptionsPlanResponse>;
        if (!response.ok || !json.ok || !json.data) {
          throw new Error(json.error ?? `Options feed failed (${response.status})`);
        }
        setOptionsFeed(json.data);
      } catch (caught) {
        setOptionsFeedError(caught instanceof Error ? caught.message : "Options feed failed");
      } finally {
        setOptionsLoading(false);
      }
    },
    [account, plan?.symbol, symbol],
  );

  // Pull options + gamma live feeds alongside the decision so the cards are not empty by default.
  useEffect(() => {
    if (!plan?.symbol) return;
    void loadGammaFeed(plan.symbol);
    void loadOptionsFeed(plan.symbol);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plan?.symbol, plan?.asof_utc]);

  // Synchronize manual override sizer defaults with new plan details
  useEffect(() => {
    if (plan) {
      const entryVal = plan.live?.price || plan.model?.entry || 100;
      setOverrideEntry(entryVal);
      const isShort = plan.live?.go_short && !plan.live?.go_long;
      const stopVal = plan.model?.stop || (isShort ? entryVal * 1.05 : entryVal * 0.95);
      setOverrideStop(Number(stopVal.toFixed(2)));
      
      const riskPerShare = Math.abs(entryVal - stopVal);
      const maxLoss = 50; // default $50 risk for $1k account
      const sharesVal = riskPerShare > 0 ? Math.max(1, Math.floor(maxLoss / riskPerShare)) : 1;
      setOverrideShares(sharesVal);
    }
  }, [plan]);

  const overrideOrder = useMemo(() => {
    if (!plan) return null;
    const isShort = plan.live?.go_short && !plan.live?.go_long;
    return {
      symbol: plan.symbol,
      side: isShort ? ("short" as const) : ("long" as const),
      shares: overrideShares,
      entry: overrideEntry,
      stop: overrideStop,
      dollarRisk: overrideShares * Math.abs(overrideEntry - overrideStop),
      model: plan.model?.model || plan.model_used || "auto",
      account: account,
    };
  }, [plan, overrideShares, overrideEntry, overrideStop, account]);

  const freshness = plan?.live?.freshness ?? plan?.confidence?.data_freshness;
  const feed = useMemo(() => feedPresentation(freshness), [freshness]);
  const decision = useMemo(() => (plan ? decisionPresentation(plan) : null), [plan]);
  // Executable size only from buildPaperOrder (gates + real stop + positive max_loss).
  // Never invent shares/stop on stand-aside — that fabricated risk and unlocks false fills.
  const order = useMemo(() => (plan ? buildPaperOrder(plan) : null), [plan]);
  const ticketView = useMemo(() => (plan ? ticketDisplayFromPlan(plan) : null), [plan]);
  const setupLabel = plan ? analysisSetupLabel(plan) : "—";
  const riskLabel = plan ? riskModeLabel(plan) : "—";
  const gex = gammaFeed ?? plan?.gex ?? null;
  const optionsCtx = optionsFeed?.structure ?? plan?.options ?? null;
  const gammaRead = useMemo(() => gammaMethodology(gex), [gex]);
  const readinessBlockers = plan?.execution_readiness?.blockers ?? [];
  const reasons = readinessBlockers.length
    ? readinessBlockers
    : plan?.confidence?.reasons ?? plan?.decision?.reasons ?? [];

  return (
    <div className="exec-workspace">
      <section className="exec-command" aria-label="Build an execution decision">
        <div className="exec-command__lead">
          <span className="td-eyebrow">START HERE</span>
          <strong>What are you considering trading?</strong>
          <p>Enter one symbol, then the desk verifies the feed before showing any action.</p>
        </div>
        <form
          className="exec-command__form"
          onSubmit={(event) => {
            event.preventDefault();
            void runPlan();
          }}
        >
          <label className="td-field exec-command__symbol">
            <span className="td-label">Symbol</span>
            <div className="exec-input-icon">
              <Search aria-hidden="true" />
              <input
                value={symbol}
                onChange={(event) => setSymbol(event.target.value.toUpperCase())}
                className="td-input"
                placeholder="APLD"
                aria-label="Symbol"
                autoComplete="off"
              />
            </div>
          </label>
          <label className="td-field exec-command__account">
            <span className="td-label">Account value</span>
            <input
              type="number"
              min={1}
              value={account}
              onChange={(event) => setAccount(Math.max(1, Number(event.target.value) || 1))}
              className="td-input tabular"
              aria-label="Account value"
            />
          </label>
          <button
            type="submit"
            className="td-btn td-btn-primary exec-command__analyze"
            disabled={loading || !symbol.trim()}
          >
            {loading ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : <Crosshair className="size-4" aria-hidden="true" />}
            {loading ? "Verifying…" : "Build decision"}
          </button>
          <button
            type="button"
            className="td-btn td-btn-ghost"
            onClick={() => void runScan()}
            disabled={scanning || loading}
          >
            {scanning ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : <Radar className="size-4" aria-hidden="true" />}
            {scanning ? "Scanning…" : "Scan market"}
          </button>
        </form>
      </section>

      {error ? (
        <div className="td-alert td-alert--error" role="alert">
          <AlertTriangle aria-hidden="true" className="size-4" />
          {error}
        </div>
      ) : null}

      {scan?.rows?.length ? (
        <section className="exec-scan-strip" aria-label="Market scan results">
          <div>
            <span className="td-eyebrow">MARKET SCAN</span>
            <strong>Choose a name to verify</strong>
          </div>
          <div className="exec-scan-strip__rows">
            {scan.rows.slice(0, 8).map((row: LiveScanRow) => (
              <button
                type="button"
                key={row.symbol}
                className="exec-scan-pick"
                onClick={() => void runPlan(row.symbol)}
              >
                <span>{row.symbol}</span>
                <small>{row.confidence_state ?? row.mode}</small>
                <b>{formatUsd(row.price)}</b>
              </button>
            ))}
          </div>
        </section>
      ) : null}

      {!plan && !loading ? (
        <section className="exec-onboard" aria-label="How to build a paper decision">
          <header>
            <span className="td-eyebrow">YOUR PAPER-TRADE PATH</span>
            <h2>Find it. Check it. Plan it.</h2>
          </header>
          <div className="exec-onboard__flow">
            <article className="exec-onboard__card exec-onboard__card--discover">
              <div className="exec-onboard__icon"><BarChart3 aria-hidden="true" /></div>
              <span>STEP 1</span>
              <h3>Find a stock</h3>
              <div className="exec-onboard__bars" aria-hidden="true">
                {[28, 42, 36, 58, 49, 72, 64, 84].map((height, index) => <i key={index} style={{ height: `${height}%` }} />)}
              </div>
              <div className="exec-onboard__links">
                <Link href={liveHref(undefined, "picks", account)}>Picks</Link>
                <Link href={watchHref(undefined, account)}>Watchlist</Link>
                <button type="button" onClick={() => void runScan()}>Scan now</button>
              </div>
            </article>
            <ArrowRight className="exec-onboard__arrow" aria-hidden="true" />
            <article className="exec-onboard__card exec-onboard__card--verify">
              <div className="exec-onboard__icon"><ShieldCheck aria-hidden="true" /></div>
              <span>STEP 2</span>
              <h3>Pass the checks</h3>
              <div className="exec-onboard__checks">
                <div><i>1</i><span>Fresh price</span><b>—</b></div>
                <div><i>2</i><span>Model agrees</span><b>—</b></div>
                <div><i>3</i><span>Risk fits</span><b>—</b></div>
                <div><i>4</i><span>Stop is valid</span><b>—</b></div>
              </div>
            </article>
            <ArrowRight className="exec-onboard__arrow" aria-hidden="true" />
            <article className="exec-onboard__card exec-onboard__card--ticket">
              <div className="exec-onboard__icon"><TicketCheck aria-hidden="true" /></div>
              <span>STEP 3</span>
              <h3>Get one paper plan</h3>
              <div className="exec-onboard__ticket">
                <div><span>ENTRY</span><b>—</b></div>
                <div><span>STOP</span><b>—</b></div>
                <div><span>SIZE</span><b>—</b></div>
                <strong>WAITING FOR A SYMBOL</strong>
              </div>
            </article>
          </div>
          <footer><span>Nothing is sent to a broker.</span><span>Every paper plan shows its maximum loss.</span></footer>
        </section>
      ) : null}

      {plan && decision ? (
        <>
          <section className="exec-trust-rail" aria-label="Market data trust status">
            <div className={`exec-trust-rail__state exec-trust-rail__state--${feed.tone}`}>
              {feed.canUse ? <Radio aria-hidden="true" /> : <AlertTriangle aria-hidden="true" />}
              <span>DATA STATUS</span>
              <strong>{feed.label}</strong>
            </div>
            <div>
              <span>SOURCE</span>
              <strong>{plan.live?.source?.toUpperCase() ?? "UNKNOWN"} · {plan.live?.interval ?? "—"}</strong>
            </div>
            <div>
              <span>AS OF</span>
              <strong>{formatAsOf(freshness?.asof_utc ?? plan.live?.timestamp)}</strong>
            </div>
            <div>
              <span>SESSION</span>
              <strong>{freshness?.market_session ?? plan.live?.market_session ?? "unknown"}</strong>
            </div>
            <div>
              <span>PRICE CHECK</span>
              <strong>{plan.gex?.price_consistent === false ? "Conflict — blocked" : "Sources aligned"}</strong>
            </div>
            <button type="button" onClick={() => void runPlan(plan.symbol)} disabled={loading} aria-label="Refresh decision">
              <RefreshCw aria-hidden="true" className={loading ? "animate-spin" : ""} />
            </button>
          </section>

          <section className={`exec-decision exec-decision--${decision.eyebrow === "SETUP READY" ? "ready" : decision.eyebrow === "NO TRADE YET" ? "watch" : "blocked"}`}>
            <div className="exec-decision__summary">
              <div className="exec-decision__identity">
                <span className="td-eyebrow">{decision.eyebrow}</span>
                <div>
                  <h2>{decision.title}</h2>
                  <div className="flex flex-wrap gap-2">
                    <Chip
                      label={`Setup ${setupLabel}`}
                      colorVar={colorVarFor("action", setupLabel)}
                    />
                    <Chip
                      label={`Risk ${riskLabel}`}
                      colorVar={colorVarFor("mode", riskLabel)}
                    />
                    <Chip
                      label={`Gate ${plan.confidence?.state ?? "ABSTAIN"}`}
                      colorVar={colorVarFor("mode", plan.confidence?.state === "ENTER" ? "EQUITY_HEDGE" : "STAND_ASIDE")}
                    />
                  </div>
                </div>
                <p>{decision.detail}</p>
                <p className="text-[11px] leading-snug" style={{ color: "var(--td-ink-500)", marginTop: 6 }}>
                  <strong style={{ color: "var(--td-ink-300)" }}>Three different things:</strong>{" "}
                  Analysis setup = what the model wants to do · Risk mode = vehicle (equity / options / cash) ·
                  Paper order unlock = only when every execution gate passes. A locked paper order does not erase the setup.
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Link href={analyzeHref({ symbol: plan.symbol })} className="td-btn td-btn-ghost no-underline">
                    Open Analyze
                  </Link>
                  <Link href={optionsHref(plan.symbol, account)} className="td-btn td-btn-ghost no-underline">
                    Options live feed
                  </Link>
                  <Link href={gammaHref(plan.symbol, account)} className="td-btn td-btn-ghost no-underline">
                    Gamma live feed
                  </Link>
                </div>
              </div>
              <div className="exec-decision__quote">
                <span>{plan.symbol}</span>
                <strong>{formatUsd(plan.live?.price)}</strong>
                <small>{plan.model?.model ?? "auto model"}</small>
              </div>
            </div>

            <div className="exec-decision__body">
              <div className="exec-decision__evidence">
                <span className="td-eyebrow mb-3 block">VERIFICATION CHECKLIST</span>
                <ul className="flex flex-col gap-3 mt-3 list-none p-0">
                  {Object.entries(plan.execution_readiness?.checks || {}).map(([key, check]: [string, { passed?: boolean; detail?: string }]) => {
                    const passed = check.passed;
                    const displayName = key
                      .replace(/_/g, " ")
                      .replace(/\b\w/g, (c) => c.toUpperCase());
                    return (
                      <li key={key} className="flex items-start gap-2 text-[12px] leading-snug">
                        {passed ? (
                          <CheckCircle2 size={14} className="shrink-0 mt-0.5" style={{ color: "var(--td-success)" }} />
                        ) : (
                          <AlertTriangle size={14} className="shrink-0 mt-0.5" style={{ color: "var(--td-gate-fail)" }} />
                        )}
                        <div>
                          <strong style={{ color: passed ? "var(--td-ink-300)" : "var(--td-muted)", fontWeight: passed ? 600 : 400 }}>
                            {displayName}
                          </strong>
                          <span className="block text-[11px] text-[var(--td-muted)]">
                            {check.detail}
                          </span>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>

              <div className="exec-decision__order">
                <span className="td-eyebrow block mb-3">SIMULATED TRADE TICKET SUGGESTION</span>
                {ticketView ? (
                  <div className="mb-4">
                    <div className="exec-order-grid mb-4">
                      <Stat label="Side" value={ticketView.side.toUpperCase()} emphasize />
                      <Stat
                        label={ticketView.executable ? "Entry" : "Mark / entry"}
                        value={formatUsd(ticketView.entry)}
                        emphasize
                      />
                      <Stat
                        label="Stop"
                        value={ticketView.stop != null ? formatUsd(ticketView.stop) : "—"}
                        emphasize
                      />
                      <Stat
                        label="Shares"
                        value={ticketView.shares != null ? String(ticketView.shares) : "—"}
                        emphasize
                      />
                      <Stat
                        label={ticketView.executable ? "Planned risk" : "Risk budget (backend)"}
                        value={
                          ticketView.executable
                            ? formatUsd(ticketView.dollarRisk, 0)
                            : formatUsd(ticketView.maxLossBudget, 0)
                        }
                        emphasize
                      />
                      <Stat
                        label="Account"
                        value={formatUsd(ticketView.account ?? plan.account ?? account, 0)}
                        emphasize
                      />
                    </div>
                    {!ticketView.executable && !showOverride ? (
                      <p className="text-[11px] mb-3" style={{ color: "var(--td-muted)" }}>
                        Action <strong>{ticketView.action}</strong> — shares and sized risk only appear when
                        every execution gate passes. The desk does not invent stop levels or force ≥1 share.
                      </p>
                    ) : null}

                    {order ? (
                      <div
                        className="p-3 mb-4 text-[12px] flex items-center gap-2 border"
                        style={{
                          background: "color-mix(in oklch, var(--td-gate-pass) 8%, transparent)",
                          borderColor: "color-mix(in oklch, var(--td-gate-pass) 28%, transparent)",
                          borderRadius: "var(--td-radius-md)",
                          color: "var(--td-gate-pass)",
                        }}
                      >
                        <CheckCircle2 className="shrink-0" size={16} />
                        <span>All live verification checks passed. Order calculation unlocked.</span>
                      </div>
                    ) : (
                      <div
                        className="p-4 mb-4 flex flex-col gap-2.5 border"
                        style={{
                          background: "color-mix(in oklch, var(--td-gate-fail) 6%, transparent)",
                          borderColor: "color-mix(in oklch, var(--td-gate-fail) 24%, transparent)",
                          borderRadius: "var(--td-radius-md)",
                        }}
                      >
                        <div
                          className="flex items-center justify-between gap-2 text-[12px] font-medium"
                          style={{ color: "var(--td-gate-fail)" }}
                        >
                          <div className="flex items-center gap-2">
                            <AlertTriangle className="shrink-0" size={16} />
                            <span>
                              Paper fill locked — stand-aside / failed gates.
                            </span>
                          </div>
                          {!showOverride && (
                            <button
                              type="button"
                              className="td-btn td-btn-ghost text-[11px] underline"
                              onClick={() => setShowOverride(true)}
                            >
                              Override gates
                            </button>
                          )}
                        </div>
                      </div>
                    )}

                    {order ? (
                      <PaperExecution order={order} plan={plan} override={false} />
                    ) : showOverride && overrideOrder ? (
                      <div className="mt-4 p-4 border border-[var(--td-hairline)] rounded-lg bg-[var(--td-surface-soft)]">
                        <div className="flex items-center justify-between mb-4 pb-2 border-b border-[var(--td-hairline)]">
                          <span className="text-[12px] font-bold uppercase tracking-wider text-[var(--td-warning)]">Manual Override Sizer</span>
                          <button
                            type="button"
                            className="text-[11px] text-[var(--td-muted)] hover:text-[var(--td-ink-300)]"
                            onClick={() => setShowOverride(false)}
                          >
                            Disable Override
                          </button>
                        </div>
                        <div className="grid grid-cols-3 gap-3 mb-4">
                          <label className="td-field">
                            <span className="td-label">Shares</span>
                            <input
                              type="number"
                              min={1}
                              value={overrideShares}
                              onChange={(e) => setOverrideShares(Math.max(1, Number(e.target.value) || 1))}
                              className="td-input tabular"
                            />
                          </label>
                          <label className="td-field">
                            <span className="td-label">Entry price</span>
                            <input
                              type="number"
                              step="0.01"
                              min="0.01"
                              value={overrideEntry}
                              onChange={(e) => setOverrideEntry(Math.max(0.01, Number(e.target.value) || 0.01))}
                              className="td-input tabular"
                            />
                          </label>
                          <label className="td-field">
                            <span className="td-label flex items-center justify-between">
                              <span>Stop level</span>
                              <button
                                type="button"
                                className="text-[9px] text-[var(--td-muted)]"
                                onClick={() => {
                                  const isShort = plan.live?.go_short && !plan.live?.go_long;
                                  const side = isShort ? 1.05 : 0.95;
                                  setOverrideStop(Number((overrideEntry * side).toFixed(2)));
                                }}
                              >
                                5% stop
                              </button>
                            </span>
                            <input
                              type="number"
                              step="0.01"
                              min="0.01"
                              value={overrideStop}
                              onChange={(e) => setOverrideStop(Math.max(0.01, Number(e.target.value) || 0.01))}
                              className="td-input tabular"
                            />
                          </label>
                        </div>
                        <div className="flex items-center justify-between mb-4 text-[12px] text-[var(--td-muted)]">
                          <span>Risk per share: <strong style={{ color: "var(--td-ink-300)" }}>{formatUsd(Math.abs(overrideEntry - overrideStop))}</strong></span>
                          <span>Max Loss: <strong style={{ color: "var(--td-ink-300)" }}>{formatUsd(Math.abs(overrideEntry - overrideStop) * overrideShares)}</strong></span>
                          <span>Notional: <strong style={{ color: "var(--td-ink-300)" }}>{formatUsd(overrideEntry * overrideShares)}</strong></span>
                        </div>
                        <PaperExecution order={overrideOrder} plan={plan} override={true} />
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <p className="text-[13px] text-[var(--td-muted)]">No ticket details available.</p>
                )}

                {/* Readiness Details Accordion */}
                <div className="border-t border-[var(--td-hairline)] pt-3 mt-2">
                  <button
                    type="button"
                    onClick={() => setShowReadinessDetails(!showReadinessDetails)}
                    className="td-btn td-btn-ghost text-[11px] uppercase tracking-wider font-semibold flex items-center gap-1.5"
                  >
                    {showReadinessDetails ? "Hide Readiness Details" : "Show Readiness Details"}
                  </button>
                  {showReadinessDetails && (
                    <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="p-3 bg-[var(--td-surface-soft)] border border-[var(--td-hairline)] rounded-lg">
                        <span className="td-eyebrow mb-2 block">Failed checks</span>
                        <ul className="list-none p-0 m-0 flex flex-col gap-1.5 text-[12px]">
                          {(reasons.length ? reasons : ["No active entry edge"]).map((reason) => (
                            <li key={reason} className="flex items-start gap-2 text-[var(--td-ink-300)]">
                              <AlertTriangle size={13} className="shrink-0 mt-0.5" style={{ color: "var(--td-gate-fail)" }} />
                              <span>{cleanReason(reason)}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                      <div className="p-3 bg-[var(--td-surface-soft)] border border-[var(--td-hairline)] rounded-lg flex flex-col gap-2 justify-between">
                        <span className="td-eyebrow block">Metrics Context</span>
                        <div className="grid grid-cols-2 gap-3">
                          <Stat label="Confidence gate" value={plan.confidence?.state ?? "ABSTAIN"} />
                          <Stat
                            label="Calibrated prob"
                            value={plan.confidence?.calibrated_probability == null ? "Unavailable" : formatPct(plan.confidence.calibrated_probability)}
                          />
                          <Stat label="Max loss" value={formatUsd(plan.ticket?.max_loss_dollars, 0)} />
                          <Stat label="Volatility z" value={formatNum(plan.live?.vol_z, 2)} />
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </section>

          <div className="exec-context-grid">
            <section className="exec-context-card">
              <div className="exec-context-card__head">
                <div>
                  <span className="td-eyebrow">GAMMA LIVE FEED</span>
                  <strong>{gex ? gammaRead.label : "Not loaded"}</strong>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="td-btn td-btn-primary"
                    onClick={() => void loadGammaFeed(plan.symbol)}
                    disabled={gammaLoading}
                  >
                    {gammaLoading ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : <Radio className="size-4" aria-hidden="true" />}
                    {gammaLoading ? "Loading…" : gex ? "Refresh gamma" : "Load live gamma"}
                  </button>
                  <Link href={gammaHref(plan.symbol, account)} className="td-btn td-btn-ghost no-underline">
                    Full gamma desk
                  </Link>
                </div>
              </div>
              {gammaFeedError ? (
                <p className="td-alert td-alert--error" role="alert">{gammaFeedError}</p>
              ) : null}
              {gex ? (
                <>
                  <p>{gammaRead.detail}</p>
                  <div className="exec-context-stats">
                    <Stat label="Gamma spot" value={formatUsd(gex.spot)} />
                    <Stat label="Regime" value={gex.regime?.replaceAll("_", " ") ?? "—"} />
                    <Stat label="Call wall" value={formatUsd(gex.call_wall)} />
                    <Stat label="Put wall" value={formatUsd(gex.put_wall)} />
                    <Stat
                      label="Squeeze"
                      value={
                        gex.squeeze_label === "bullish_squeeze"
                          ? `Upside ${formatNum(gex.squeeze_score, 1)}`
                          : gex.squeeze_label === "bearish_squeeze"
                            ? `Downside ${formatNum(gex.squeeze_score, 1)}`
                            : `None ${formatNum(gex.squeeze_score ?? 0, 1)}`
                      }
                    />
                    <Stat
                      label="Expected move"
                      value={
                        gex.expected_move_pct == null
                          ? "—"
                          : `±${formatPctPoints(gex.expected_move_pct).replace("+", "")}`
                      }
                    />
                  </div>
                  {(gex.warnings ?? []).slice(0, 1).map((warning) => (
                    <small key={warning}>{warning}</small>
                  ))}
                </>
              ) : (
                <p>
                  No gamma snapshot on this decision yet. Press <strong>Load live gamma</strong> to pull
                  walls, squeeze, and expected move from the options chain.
                </p>
              )}
            </section>

            <section className="exec-context-card">
              <div className="exec-context-card__head">
                <div>
                  <span className="td-eyebrow">OPTIONS LIVE FEED</span>
                  <strong>
                    {optionsCtx?.structure
                      ? optionsCtx.structure.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase())
                      : optionsCtx
                        ? "No structure"
                        : "Not loaded"}
                  </strong>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="td-btn td-btn-primary"
                    onClick={() => void loadOptionsFeed(plan.symbol)}
                    disabled={optionsLoading}
                  >
                    {optionsLoading ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : <Radio className="size-4" aria-hidden="true" />}
                    {optionsLoading ? "Loading…" : optionsCtx ? "Refresh options" : "Load live options"}
                  </button>
                  <Link href={optionsHref(plan.symbol, account)} className="td-btn td-btn-ghost no-underline">
                    Full options desk
                  </Link>
                </div>
              </div>
              {optionsFeedError ? (
                <p className="td-alert td-alert--error" role="alert">{optionsFeedError}</p>
              ) : null}
              {optionsCtx && optionsCtx.structure ? (
                <div style={{ opacity: plan.decision?.mode === "OPTIONS_ATTACK" && optionsCtx.action === "buy" ? 1 : 0.7 }}>
                  {(plan.decision?.mode !== "OPTIONS_ATTACK" || optionsCtx.action !== "buy") && (
                    <div className="mb-2 p-2 text-[11px] border border-dashed border-[var(--td-hairline-strong)] rounded text-[var(--td-muted)] bg-[var(--td-surface-soft)]">
                      ℹ️ {optionsCtx.reason || "Reference proposal only. Option buying is inactive (stand-aside/equity mode)."}
                    </div>
                  )}
                  <p className="text-[12px] leading-relaxed mb-3">
                    {plan.decision?.mode === "OPTIONS_ATTACK" && optionsCtx.action === "buy"
                      ? "Attack path from live risk mode."
                      : "Defined-risk proposal from the live options chain. Not a green light unless risk mode is OPTIONS_ATTACK."}
                  </p>
                  <div className="exec-context-stats" style={{ filter: plan.decision?.mode === "OPTIONS_ATTACK" && optionsCtx.action === "buy" ? "none" : "grayscale(40%)" }}>
                    <Stat label="Expiry" value={optionsCtx.expiry ?? "—"} />
                    <Stat label="DTE" value={String(optionsCtx.dte ?? "—")} />
                    <Stat label="Long strike" value={formatUsd(optionsCtx.long_strike)} />
                    <Stat label="Short strike" value={formatUsd(optionsCtx.short_strike)} />
                    <Stat label="Debit/share" value={formatUsd(optionsCtx.debit_per_share)} />
                    <Stat label="Max loss" value={formatUsd(optionsCtx.max_loss_1_contract, 0)} />
                  </div>
                </div>
              ) : (
                <p className="text-[13px] text-[var(--td-muted)]">
                  {optionsCtx?.reason ||
                    optionsCtx?.error ||
                    optionsFeed?.structure_error ||
                    "No options structure yet. Press Load live options to pull the chain and a debit-spread proposal."}
                </p>
              )}
            </section>
          </div>
        </>
      ) : null}
    </div>
  );
}
