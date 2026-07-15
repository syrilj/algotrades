"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  CheckCircle2,
  Crosshair,
  Loader2,
  LockKeyhole,
  Radar,
  Radio,
  RefreshCw,
  Search,
  ShieldCheck,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Chip } from "@/components/ui/Chip";
import { Stat } from "@/components/ui/Stat";
import { colorVarFor } from "@/lib/actionColors";
import {
  buildPaperOrder,
  decisionPresentation,
  feedPresentation,
  gammaMethodology,
} from "@/lib/executionState";
import { formatNum, formatPct, formatPctPoints, formatUsd } from "@/lib/format";
import { gammaHref, liveHref, optionsHref, positionsHref, watchHref } from "@/lib/routes";
import type {
  ApiEnvelope,
  LivePlanResponse,
  LiveScanResponse,
  LiveScanRow,
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
    trusted_execution_feed: "Execution-grade LSE data is unavailable",
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
}: {
  order: PaperOrder;
  plan: LivePlanResponse;
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
          reason: "Verified in the guided Execution workspace",
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
          <strong>Paper position logged</strong>
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
        <span className="td-eyebrow">PAPER EXECUTION</span>
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

  const freshness = plan?.live?.freshness ?? plan?.confidence?.data_freshness;
  const feed = useMemo(() => feedPresentation(freshness), [freshness]);
  const decision = useMemo(() => (plan ? decisionPresentation(plan) : null), [plan]);
  const order = useMemo(() => (plan ? buildPaperOrder(plan) : null), [plan]);
  const gammaRead = useMemo(() => gammaMethodology(plan?.gex), [plan?.gex]);
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
        <section className="exec-empty">
          <div className="exec-empty__mark"><ShieldCheck aria-hidden="true" /></div>
          <div>
            <span className="td-eyebrow">GUIDED EXECUTION</span>
            <h2>Evidence before action.</h2>
            <p>
              The desk will verify the price source, market timestamp, model gate, risk budget,
              and options context before it unlocks a paper order.
            </p>
            <p className="td-muted" style={{ marginTop: "0.75rem" }}>
              No name yet? Discover first:{" "}
              <Link href={liveHref(undefined, "bias", account)} className="no-underline">
                Bias
              </Link>
              {" · "}
              <Link href={liveHref(undefined, "picks", account)} className="no-underline">
                Picks
              </Link>
              {" · "}
              <Link href={watchHref(undefined, account)} className="no-underline">
                Watch
              </Link>
              , or run <strong>Scan market</strong> above for an execution-grade shortlist.
            </p>
          </div>
          <ol>
            <li><span>01</span> Choose a symbol</li>
            <li><span>02</span> Verify the feed</li>
            <li><span>03</span> Follow one decision</li>
          </ol>
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
                  <Chip
                    label={plan.ticket?.mode ?? plan.confidence?.state ?? "—"}
                    colorVar={colorVarFor("mode", plan.ticket?.mode)}
                  />
                </div>
                <p>{decision.detail}</p>
              </div>
              <div className="exec-decision__quote">
                <span>{plan.symbol}</span>
                <strong>{formatUsd(plan.live?.price)}</strong>
                <small>{plan.model?.model ?? "auto model"}</small>
              </div>
            </div>

            <div className="exec-decision__body">
              <div className="exec-decision__evidence">
                <span className="td-eyebrow">WHY THIS DECISION</span>
                <ul>
                  {(reasons.length ? reasons : ["No confirmed live entry edge"]).slice(0, 4).map((reason) => (
                    <li key={reason}>
                      {order ? <CheckCircle2 aria-hidden="true" /> : <LockKeyhole aria-hidden="true" />}
                      {cleanReason(reason)}
                    </li>
                  ))}
                </ul>
                <div className="exec-confidence-line">
                  <Stat label="Confidence gate" value={plan.confidence?.state ?? "ABSTAIN"} emphasize />
                  <Stat
                    label="Calibrated probability"
                    value={plan.confidence?.calibrated_probability == null ? "Unavailable" : formatPct(plan.confidence.calibrated_probability)}
                    emphasize
                  />
                  <Stat label="Max loss" value={formatUsd(plan.ticket?.max_loss_dollars, 0)} emphasize />
                  <Stat label="Volatility z" value={formatNum(plan.live?.vol_z, 2)} emphasize />
                </div>
              </div>

              <div className="exec-decision__order">
                {order ? (
                  <>
                    <div className="exec-order-grid">
                      <Stat label="Side" value={order.side.toUpperCase()} emphasize />
                      <Stat label="Entry" value={formatUsd(order.entry)} emphasize />
                      <Stat label="Stop" value={formatUsd(order.stop)} emphasize />
                      <Stat label="Shares" value={String(order.shares)} emphasize />
                      <Stat label="Planned risk" value={formatUsd(order.dollarRisk, 0)} emphasize />
                      <Stat label="Account" value={formatUsd(order.account, 0)} emphasize />
                    </div>
                    <PaperExecution order={order} plan={plan} />
                  </>
                ) : (
                  <div className="exec-locked">
                    <LockKeyhole aria-hidden="true" />
                    <div>
                      <span className="td-eyebrow">EXECUTION LOCKED</span>
                      <strong>No order is available</strong>
                      <p>The desk needs fresh data, an ENTER confidence gate, and valid entry/stop risk before it can size an order.</p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </section>

          <div className="exec-context-grid">
            <section className="exec-context-card">
              <div className="exec-context-card__head">
                <div>
                  <span className="td-eyebrow">GAMMA CONTEXT</span>
                  <strong>{gammaRead.label}</strong>
                </div>
                <Link href={gammaHref(plan.symbol, account)} className="td-btn td-btn-ghost no-underline">Open detail</Link>
              </div>
              {plan.gex ? (
                <>
                  <p>{gammaRead.detail}</p>
                  <div className="exec-context-stats">
                    <Stat label="Gamma spot" value={formatUsd(plan.gex.spot)} />
                    <Stat label="Regime" value={plan.gex.regime?.replaceAll("_", " ") ?? "—"} />
                    <Stat label="Call wall" value={formatUsd(plan.gex.call_wall)} />
                    <Stat label="Put wall" value={formatUsd(plan.gex.put_wall)} />
                    <Stat label="Expected move" value={plan.gex.expected_move_pct == null ? "—" : `±${formatPctPoints(plan.gex.expected_move_pct).replace("+", "")}`} />
                    <Stat label="Price divergence" value={formatPctPoints(plan.gex.price_divergence_pct ?? 0)} />
                  </div>
                  {(plan.gex.warnings ?? []).slice(0, 1).map((warning) => <small key={warning}>{warning}</small>)}
                </>
              ) : <p>Gamma context is unavailable. It is never required to force a trade.</p>}
            </section>

            <section className="exec-context-card">
              <div className="exec-context-card__head">
                <div>
                  <span className="td-eyebrow">OPTIONS CONTEXT</span>
                  <strong>{plan.options?.action === "buy" ? plan.options.structure : "No options attack"}</strong>
                </div>
                <Link href={optionsHref(plan.symbol, account)} className="td-btn td-btn-ghost no-underline">Open detail</Link>
              </div>
              {plan.options?.action === "buy" ? (
                <>
                  <p>Defined-risk structure generated from the same verified symbol and account.</p>
                  <div className="exec-context-stats">
                    <Stat label="Expiry" value={plan.options.expiry ?? "—"} />
                    <Stat label="DTE" value={String(plan.options.dte ?? "—")} />
                    <Stat label="Long strike" value={formatUsd(plan.options.long_strike)} />
                    <Stat label="Short strike" value={formatUsd(plan.options.short_strike)} />
                    <Stat label="Debit/share" value={formatUsd(plan.options.debit_per_share)} />
                    <Stat label="Max loss" value={formatUsd(plan.options.max_loss_1_contract, 0)} />
                  </div>
                </>
              ) : (
                <p>{plan.options?.reason ?? plan.options?.error ?? "The verified decision does not call for an options structure."}</p>
              )}
            </section>
          </div>
        </>
      ) : null}
    </div>
  );
}
