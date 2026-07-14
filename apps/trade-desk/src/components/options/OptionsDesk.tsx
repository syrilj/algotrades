"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ListChecks } from "lucide-react";
import type { ApiEnvelope, OptionsPlanResponse } from "@/lib/types";
import { formatNum, formatUsd } from "@/lib/format";
import { PageHeader } from "@/components/shell/PageHeader";
import { analyzeHref, liveHref } from "@/lib/routes";
import { Chip } from "@/components/ui/Chip";
import { EmptyState } from "@/components/ui/EmptyState";
import { Stat } from "@/components/ui/Stat";
import { colorVarFor } from "@/lib/actionColors";

function OptionsDeskInner({ showHeader = true }: { showHeader?: boolean }) {
  const searchParams = useSearchParams();
  const qSymbol = searchParams.get("symbol")?.toUpperCase() ?? "";

  const [symbol, setSymbol] = useState(qSymbol || "APLD");
  const [account, setAccount] = useState(1000);
  const [riskPct, setRiskPct] = useState(18);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [plan, setPlan] = useState<OptionsPlanResponse | null>(null);

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
      try {
        const res = await fetch("/api/options-plan", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            symbol: sym,
            account,
            risk_pct: riskPct,
            peak: account,
          }),
        });
        const json = (await res.json()) as ApiEnvelope<OptionsPlanResponse>;
        if (!res.ok || json.ok === false || !json.data) {
          throw new Error(json.error ?? `options-plan failed (${res.status})`);
        }
        setPlan(json.data);
      } catch (e) {
        setError(e instanceof Error ? e.message : "options plan failed");
      } finally {
        setLoading(false);
      }
    },
    [symbol, account, riskPct],
  );

  useEffect(() => {
    if (!qSymbol) return;
    void run(qSymbol);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qSymbol]);

  const structure = plan?.structure;
  const isBuy = structure?.action === "buy";
  const attack =
    plan?.mode?.toUpperCase().includes("OPTIONS") === true && isBuy;

  const body = (
    <>
      {showHeader && <PageHeader
        title="Options"
        description="Structure + risk mode + what to do. Live strikes from the picker; v22 robust is research only."
        actions={
          symbol ? (
            <div className="flex flex-wrap gap-2">
              <Link
                href={analyzeHref({ symbol })}
                className="td-btn td-btn-ghost no-underline"
              >
                Analyze
              </Link>
              <Link href={liveHref(symbol)} className="td-btn td-btn-ghost no-underline">
                Live
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
          <label className="td-field td-field--risk">
            <span className="td-label">Max risk %</span>
            <input
              type="number"
              value={riskPct}
              onChange={(e) => setRiskPct(Number(e.target.value))}
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
            {loading ? "Planning…" : "Plan options"}
          </button>
        </div>
        <p className="text-[11px]" style={{ color: "var(--td-ink-500)" }}>
          Prefer APLD / IONQ on small books · avoid MU ATM weeklies · default bull call debit
          spread 14–45 DTE
        </p>
      </section>

      {error ? (
        <p className="td-alert td-alert--error" role="alert">
          {error}
        </p>
      ) : null}

      {!plan && !loading && !error ? (
        <section className="td-panel p-5">
          <EmptyState
            icon={ListChecks}
            title="No structure yet"
            steps={[
              "Enter symbol (start with APLD or IONQ)",
              "Plan options → read mode + do next",
              "Only size when mode is OPTIONS_ATTACK and structure is buy",
            ]}
          />
        </section>
      ) : null}

      {plan ? (
        <div className="grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
          <section
            className="td-panel flex flex-col gap-4 p-5"
            style={{ borderLeft: `3px solid ${colorVarFor("mode", plan.mode)}` }}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <span className="td-label">Ticket</span>
                <div className="flex flex-wrap items-baseline gap-3">
                  <span
                    className="text-[28px] font-medium"
                    style={{
                      fontFamily: "var(--td-font-display)",
                      color: "var(--td-ink-50)",
                    }}
                  >
                    {plan.symbol}
                  </span>
                  <span style={{ color: "var(--td-ink-300)" }}>
                    {formatUsd(plan.live?.price ?? structure?.spot)}
                  </span>
                </div>
              </div>
              <Chip label={plan.mode ?? "—"} colorVar={colorVarFor("mode", plan.mode)} />
            </div>

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat label="Vehicle" value={plan.vehicle} />
              <Stat
                label="Go long"
                value={plan.live?.go_long == null ? "—" : String(plan.live.go_long)}
              />
              <Stat label="Vol z" value={formatNum(plan.live?.vol_z, 2)} />
              <Stat
                label="Macro"
                value={
                  plan.macro?.defensive
                    ? "defensive"
                    : plan.macro?.macro_ok === false
                      ? "blocked"
                      : plan.macro?.qqq_trend ?? "—"
                }
              />
            </div>

            <div>
              <span className="td-label">Do this</span>
              <ol className="mt-1 flex flex-col gap-1.5">
                {plan.do_next.map((s, i) => (
                  <li
                    key={`${i}-${s.slice(0, 20)}`}
                    className="flex gap-2 text-[14px] leading-snug"
                    style={{
                      color: attack ? "var(--td-ink-50)" : "var(--td-ink-200)",
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
            </div>

            {plan.live_error ? (
              <p className="text-[12px]" style={{ color: "var(--td-action-breakout-watch)" }}>
                Live mode partial: {plan.live_error.slice(0, 160)}
              </p>
            ) : null}
          </section>

          <section className="td-panel flex flex-col gap-3 p-5">
            <span className="td-label">Structure</span>
            {isBuy ? (
              <>
                <p
                  className="text-[17px] font-medium"
                  style={{ color: "var(--td-ink-50)" }}
                >
                  {structure?.structure}
                </p>
                {!attack ? (
                  <p
                    className="text-[12px]"
                    style={{ color: "var(--td-action-breakout-watch)" }}
                  >
                    Proposal only — risk mode is not OPTIONS_ATTACK. Do not size from this alone.
                  </p>
                ) : (
                  <p
                    className="text-[12px]"
                    style={{ color: "var(--td-action-buy-now)" }}
                  >
                    Attack mode + buy structure — defined-risk size within budget.
                  </p>
                )}
                <div
                  className="grid grid-cols-2 gap-2 text-[13px]"
                  style={{ color: "var(--td-ink-200)" }}
                >
                  <span>
                    Expiry {structure?.expiry} ({structure?.dte}d)
                  </span>
                  <span>Δ {formatNum(structure?.long_delta, 2)}</span>
                  <span>Long {structure?.long_strike}</span>
                  <span>Short {structure?.short_strike ?? "—"}</span>
                  <span>Debit {formatUsd(structure?.debit_per_share)}</span>
                  <span>Max loss {formatUsd(structure?.max_loss_1_contract, 0)}</span>
                  <span>Budget {formatUsd(structure?.budget, 0)}</span>
                  <span>
                    IV{" "}
                    {structure?.iv_long != null
                      ? `${(structure.iv_long * 100).toFixed(0)}%`
                      : "—"}
                  </span>
                </div>
                {(structure?.warnings ?? []).map((w) => (
                  <p
                    key={w}
                    className="text-[12px]"
                    style={{ color: "var(--td-action-breakout-watch)" }}
                  >
                    WARN: {w}
                  </p>
                ))}
                {structure?.exit_plan ? (
                  <div>
                    <span className="td-label">Exit plan</span>
                    <div className="mt-1 flex flex-col gap-1">
                      {Object.entries(structure.exit_plan).map(([k, v]) => (
                        <div
                          key={k}
                          className="text-[12px]"
                          style={{ color: "var(--td-ink-300)" }}
                        >
                          <span style={{ color: "var(--td-ink-500)" }}>{k}: </span>
                          {v}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </>
            ) : (
              <p className="text-[13px]" style={{ color: "var(--td-ink-300)" }}>
                {structure?.reason ||
                  structure?.error ||
                  plan.structure_error ||
                  "No options structure — stand aside or equity only."}
              </p>
            )}
          </section>
        </div>
      ) : null}

      {plan ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <section className="td-panel p-4">
            <h2
              className="mb-2 text-[14px] font-medium"
              style={{ color: "var(--td-ink-100)" }}
            >
              Playbook ($1k)
            </h2>
            <p className="mb-2 text-[12px]" style={{ color: "var(--td-ink-400)" }}>
              {plan.playbook.account_fit}
            </p>
            <p className="mb-2 text-[13px]" style={{ color: "var(--td-ink-200)" }}>
              {plan.playbook.default_structure}
            </p>
            <ul className="flex flex-col gap-1.5 text-[12px]" style={{ color: "var(--td-ink-300)" }}>
              {plan.playbook.rules.map((r) => (
                <li key={r}>• {r}</li>
              ))}
            </ul>
            <p className="mt-3 text-[11px]" style={{ color: "var(--td-ink-500)" }}>
              Preferred: {plan.playbook.preferred.join(", ")} · Avoid ATM:{" "}
              {plan.playbook.avoid_atm.join(", ")}
            </p>
          </section>

          <section className="td-panel p-4">
            <h2
              className="mb-2 text-[14px] font-medium"
              style={{ color: "var(--td-ink-100)" }}
            >
              Research · v22
            </h2>
            <p className="text-[13px] leading-snug" style={{ color: "var(--td-ink-300)" }}>
              {plan.research.note}
            </p>
            <p className="mt-2 text-[12px]" style={{ color: "var(--td-ink-400)" }}>
              Recommended research variant:{" "}
              <strong style={{ color: "var(--td-ink-200)" }}>
                {plan.research.v22_variant}
              </strong>
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Link href="/robust" className="td-btn td-btn-ghost no-underline">
                Open v22 robust backtest
              </Link>
              <Link
                href={liveHref(plan.symbol)}
                className="td-btn td-btn-primary no-underline"
              >
                Confirm on Live
              </Link>
            </div>
          </section>
        </div>
      ) : null}
    </>
  );
  return showHeader ? <div className="td-page">{body}</div> : body;
}

export function OptionsDesk({ showHeader = true }: { showHeader?: boolean }) {
  return (
    <Suspense
      fallback={
        showHeader ? (
          <div className="td-page">
            <p className="td-muted">Loading options desk…</p>
          </div>
        ) : (
          <p className="td-muted">Loading options desk…</p>
        )
      }
    >
      <OptionsDeskInner showHeader={showHeader} />
    </Suspense>
  );
}
