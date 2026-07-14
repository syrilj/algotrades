"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import type {
  ApiEnvelope,
  LivePlanResponse,
  LiveScanResponse,
  LiveScanRow,
} from "@/lib/types";
import { formatUsd, formatPct, formatNum } from "@/lib/format";
import { PageHeader } from "@/components/shell/PageHeader";
import { analyzeHref, optionsHref } from "@/lib/routes";
import { Chip } from "@/components/ui/Chip";
import { colorVarFor } from "@/lib/actionColors";

function LiveDeskInner({ showHeader = true }: { showHeader?: boolean }) {
  const searchParams = useSearchParams();
  const qSymbol = searchParams.get("symbol")?.toUpperCase() ?? "";

  const [symbol, setSymbol] = useState(qSymbol || "APLD");
  const [account, setAccount] = useState(1000);
  const [peak, setPeak] = useState(1000);
  const [history, setHistory] = useState("");
  const [noModel, setNoModel] = useState(false);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [plan, setPlan] = useState<LivePlanResponse | null>(null);
  const [scan, setScan] = useState<LiveScanResponse | null>(null);

  useEffect(() => {
    if (qSymbol) setSymbol(qSymbol);
  }, [qSymbol]);

  const runPlan = useCallback(
    async (symOverride?: string) => {
      const sym = (symOverride ?? symbol).trim().toUpperCase();
      if (!sym) return;
      setSymbol(sym);
      setLoading(true);
      setError(null);
      try {
        const res = await fetch("/api/live-plan", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            symbol: sym,
            account,
            peak,
            history: history || undefined,
            noModel,
            // empty → server/live_plan uses WINNER equity (v39b_live_adapt)
            model: noModel ? undefined : "auto",
          }),
        });
        const json = (await res.json()) as ApiEnvelope<LivePlanResponse>;
        if (!res.ok || json.ok === false || !json.data) {
          throw new Error(json.error ?? `live-plan failed (${res.status})`);
        }
        setPlan(json.data);
      } catch (e) {
        setError(e instanceof Error ? e.message : "live plan failed");
      } finally {
        setLoading(false);
      }
    },
    [symbol, account, peak, history, noModel],
  );

  useEffect(() => {
    if (!qSymbol) return;
    void runPlan(qSymbol);
    // only auto-plan when deep-linked with ?symbol=
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qSymbol]);

  const runScan = useCallback(async () => {
    setScanning(true);
    setError(null);
    try {
      const res = await fetch("/api/live-plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scan: true,
          account,
          peak,
          noModel: true,
        }),
      });
      const json = (await res.json()) as ApiEnvelope<LiveScanResponse>;
      if (!res.ok || json.ok === false || !json.data) {
        throw new Error(json.error ?? `scan failed (${res.status})`);
      }
      setScan(json.data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "scan failed");
    } finally {
      setScanning(false);
    }
  }, [account, peak]);

  const ticket = plan?.ticket;
  const live = plan?.live;
  const opt = plan?.options;

  const body = (
    <>
      {showHeader && <PageHeader
        title="Live desk"
        description="Risk mode ticket: stand aside · equity hedge · options attack. Numbered steps first; features secondary."
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
                href={optionsHref(symbol)}
                className="td-btn td-btn-ghost no-underline"
              >
                Options
              </Link>
            </div>
          ) : null
        }
      />}

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
          <label className="td-field td-field--account">
            <span className="td-label">Account $</span>
            <input
              type="number"
              value={account}
              onChange={(e) => setAccount(Number(e.target.value))}
              className="td-input"
              style={{ fontFamily: "var(--td-font-mono)" }}
            />
          </label>
          <label className="td-field td-field--account">
            <span className="td-label">Peak $</span>
            <input
              type="number"
              value={peak}
              onChange={(e) => setPeak(Number(e.target.value))}
              className="td-input"
              style={{ fontFamily: "var(--td-font-mono)" }}
            />
          </label>
          <label className="td-field td-field--model">
            <span className="td-label">History (PnL signs)</span>
            <input
              value={history}
              onChange={(e) => setHistory(e.target.value)}
              placeholder="1,1,-1"
              className="td-input"
              style={{ fontFamily: "var(--td-font-mono)" }}
            />
          </label>
        </div>
        <div className="td-toolbar__row">
          <label
            className="flex items-center gap-2 text-[12px]"
            style={{ color: "var(--td-ink-300)" }}
          >
            <input
              type="checkbox"
              checked={noModel}
              onChange={(e) => setNoModel(e.target.checked)}
            />
            Fast (skip model)
          </label>
          <button
            type="button"
            onClick={() => void runPlan()}
            disabled={loading || !symbol.trim()}
            className="td-btn td-btn-primary"
          >
            {loading ? "Planning…" : "Plan live"}
          </button>
          <button
            type="button"
            onClick={() => void runScan()}
            disabled={scanning}
            className="td-btn td-btn-ghost"
          >
            {scanning ? "Scanning…" : "Scan book"}
          </button>
        </div>
      </section>

      {error ? (
        <p className="td-alert td-alert--error" role="alert">
          {error}
        </p>
      ) : null}

      {plan && ticket ? (
        <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <section
            className="td-panel flex flex-col gap-3 p-4"
            style={{ borderLeft: `3px solid ${colorVarFor("mode", ticket.mode)}` }}
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-baseline gap-3">
                <Link
                  href={analyzeHref({ symbol: plan.symbol })}
                  className="text-[28px] font-medium no-underline"
                  style={{
                    color: "var(--td-ink-50)",
                    fontFamily: "var(--td-font-display)",
                  }}
                >
                  {plan.symbol}
                </Link>
                <span className="text-[14px]" style={{ color: "var(--td-ink-300)" }}>
                  {formatUsd(live?.price)}
                </span>
              </div>
              <Chip label={ticket.mode ?? "—"} colorVar={colorVarFor("mode", ticket.mode)} />
            </div>

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat label="Vehicle" value={ticket.vehicle} />
              <Stat label="Conviction" value={formatNum(ticket.conviction, 2)} />
              <Stat label="Risk" value={formatPct(ticket.risk_pct ?? 0)} />
              <Stat label="Max loss" value={formatUsd(ticket.max_loss_dollars, 0)} />
              <Stat label="Vol z" value={formatNum(live?.vol_z, 2)} />
              <Stat label="Blended conf" value={formatPct(plan.blended_confidence ?? 0)} />
              <Stat label="QQQ" value={plan.macro?.qqq_trend ?? "—"} />
              <Stat label="Macro" value={plan.macro?.xlp_spy_ratio_state ?? "—"} />
            </div>

            <div>
              <div className="td-label mb-1">Do this</div>
              <ol className="flex flex-col gap-1.5">
                {(ticket.steps ?? ["No steps — re-run plan."]).map((s, i) => (
                  <li
                    key={s}
                    className="flex gap-2 text-[14px] leading-snug"
                    style={{
                      color: "var(--td-ink-100)",
                      fontWeight: i === 0 ? 600 : 400,
                    }}
                  >
                    <span
                      className="tabular shrink-0"
                      style={{
                        fontFamily: "var(--td-font-mono)",
                        color: "var(--td-ink-500)",
                      }}
                    >
                      {i + 1}.
                    </span>
                    <span>{s}</span>
                  </li>
                ))}
              </ol>
              {String(ticket.vehicle).includes("option") ||
              String(ticket.mode).includes("OPTIONS") ? (
                <Link
                  href={optionsHref(plan.symbol)}
                  className="td-btn td-btn-primary mt-3 no-underline"
                >
                  Open Options desk
                </Link>
              ) : null}
            </div>

            {ticket.exit_rules ? (
              <div>
                <div className="td-label mb-1">Exit rules</div>
                <div className="grid gap-1">
                  {Object.entries(ticket.exit_rules).map(([k, v]) => (
                    <div key={k} className="text-[12px]" style={{ color: "var(--td-ink-300)" }}>
                      <span style={{ color: "var(--td-ink-400)" }}>{k}:</span> {v}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </section>

          <section className="td-panel flex flex-col gap-3 p-4">
            <div className="td-label">Options structure</div>
            {opt?.action === "buy" ? (
              <>
                <p className="text-[15px] font-medium" style={{ color: "var(--td-ink-50)" }}>
                  {opt.structure}
                </p>
                <div
                  className="grid grid-cols-2 gap-2 text-[13px]"
                  style={{ color: "var(--td-ink-200)" }}
                >
                  <span>
                    Expiry {opt.expiry} ({opt.dte}d)
                  </span>
                  <span>Δ {formatNum(opt.long_delta, 2)}</span>
                  <span>Long {opt.long_strike}</span>
                  <span>Short {opt.short_strike ?? "—"}</span>
                  <span>Debit {formatUsd(opt.debit_per_share)}</span>
                  <span>Max loss {formatUsd(opt.max_loss_1_contract, 0)}</span>
                </div>
                {(opt.warnings ?? []).map((w) => (
                  <p
                    key={w}
                    className="text-[12px]"
                    style={{ color: "var(--td-action-breakout-watch)" }}
                  >
                    WARN: {w}
                  </p>
                ))}
              </>
            ) : opt?.action === "skip" || opt?.error ? (
              <p className="text-[13px]" style={{ color: "var(--td-ink-300)" }}>
                {opt.reason || opt.error || "No options structure"}
              </p>
            ) : (
              <p className="text-[13px]" style={{ color: "var(--td-ink-400)" }}>
                No options ticket (equity hedge or stand aside).
              </p>
            )}

            <details className="td-details mt-1">
              <summary className="td-details__summary">Live features · model</summary>
              <div
                className="mt-2 grid grid-cols-2 gap-2 text-[12px]"
                style={{ color: "var(--td-ink-300)" }}
              >
                <span>go_long: {String(live?.go_long)}</span>
                <span>MACD+: {String(live?.macd_positive)}</span>
                <span>above VWAP: {String(live?.above_vwap)}</span>
                <span>swing up: {String(live?.swing_uptrend)}</span>
                <span>ATR%: {formatPct(live?.atr_pct ?? 0)}</span>
                <span>DD: {formatPct(plan.drawdown ?? 0)}</span>
              </div>
              {plan.model?.ok ? (
                <div className="mt-2 text-[12px]" style={{ color: "var(--td-ink-400)" }}>
                  Model {plan.model.model} conf {formatPct(plan.model.confidence ?? 0)}
                  {plan.model.action_hint ? ` · ${plan.model.action_hint}` : ""}
                </div>
              ) : (
                <div className="mt-2 text-[12px]" style={{ color: "var(--td-ink-500)" }}>
                  Model blend{" "}
                  {plan.model?.error
                    ? `(${plan.model.error.slice(0, 80)})`
                    : "optional / skipped"}
                </div>
              )}
            </details>
          </section>
        </div>
      ) : null}

      {scan?.rows?.length ? (
        <section className="td-panel overflow-x-auto">
          <div className="flex items-center justify-between px-4 py-3">
            <span className="text-[14px] font-medium" style={{ color: "var(--td-ink-100)" }}>
              Scan · {scan.count} names
            </span>
            <span className="text-[12px]" style={{ color: "var(--td-ink-400)" }}>
              macro {scan.macro?.xlp_spy_ratio_state ?? "—"} · QQQ{" "}
              {scan.macro?.qqq_trend ?? "—"}
            </span>
          </div>
          <table className="w-full text-left text-[13px]">
            <thead>
              <tr style={{ color: "var(--td-ink-400)", borderTop: "1px solid var(--td-ink-700)" }}>
                <th className="px-4 py-2 font-normal">Symbol</th>
                <th className="px-2 py-2 font-normal">Mode</th>
                <th className="px-2 py-2 font-normal">Vehicle</th>
                <th className="px-2 py-2 font-normal">Conv</th>
                <th className="px-2 py-2 font-normal">Vol z</th>
                <th className="px-2 py-2 font-normal">Price</th>
                <th className="px-2 py-2 font-normal">Max loss</th>
                <th className="px-2 py-2 font-normal">Analyze</th>
              </tr>
            </thead>
            <tbody>
              {scan.rows.map((r: LiveScanRow) => (
                <tr
                  key={r.symbol}
                  className="td-row-link"
                  style={{ borderTop: "1px solid var(--td-ink-800)" }}
                  onClick={() => {
                    void runPlan(r.symbol);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      void runPlan(r.symbol);
                    }
                  }}
                  tabIndex={0}
                  role="button"
                >
                  <td
                    className="px-4 py-2 font-medium"
                    style={{
                      color: "var(--td-ink-50)",
                      fontFamily: "var(--td-font-mono)",
                    }}
                  >
                    {r.symbol}
                  </td>
                  <td className="px-2 py-2">
                    <span style={{ color: colorVarFor("mode", r.mode) }}>{r.mode}</span>
                  </td>
                  <td className="px-2 py-2" style={{ color: "var(--td-ink-300)" }}>
                    {r.vehicle}
                  </td>
                  <td className="px-2 py-2" style={{ color: "var(--td-ink-200)" }}>
                    {formatNum(r.conviction, 2)}
                  </td>
                  <td className="px-2 py-2" style={{ color: "var(--td-ink-200)" }}>
                    {formatNum(r.vol_z, 2)}
                  </td>
                  <td className="px-2 py-2" style={{ color: "var(--td-ink-200)" }}>
                    {formatUsd(r.price)}
                  </td>
                  <td className="px-2 py-2" style={{ color: "var(--td-ink-200)" }}>
                    {formatUsd(r.max_loss_dollars, 0)}
                  </td>
                  <td className="px-2 py-2">
                    <Link
                      href={analyzeHref({ symbol: r.symbol })}
                      className="text-[12px] no-underline"
                      style={{ color: "var(--td-brand)" }}
                      onClick={(e) => e.stopPropagation()}
                    >
                      Open →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}
    </>
  );
  return showHeader ? <div className="td-page">{body}</div> : body;
}

export function LiveDesk({ showHeader = true }: { showHeader?: boolean }) {
  return (
    <Suspense
      fallback={
        showHeader ? (
          <div className="td-page">
            <p className="td-muted">Loading live desk…</p>
          </div>
        ) : (
          <p className="td-muted">Loading live desk…</p>
        )
      }
    >
      <LiveDeskInner showHeader={showHeader} />
    </Suspense>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="td-label">{label}</span>
      <span className="text-[14px]" style={{ color: "var(--td-ink-100)" }}>
        {value}
      </span>
    </div>
  );
}
