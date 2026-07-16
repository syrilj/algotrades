"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ListChecks } from "lucide-react";
import type { ApiEnvelope, OptionsPlanResponse, UnusualOptionsFlag } from "@/lib/types";
import { formatNum, formatUsd } from "@/lib/format";
import { PageHeader } from "@/components/shell/PageHeader";
import { analyzeHref, liveHref } from "@/lib/routes";
import { Chip } from "@/components/ui/Chip";
import { EmptyState } from "@/components/ui/EmptyState";
import { Stat } from "@/components/ui/Stat";
import { colorVarFor } from "@/lib/actionColors";

function severityColor(severity: string | undefined): string {
  if (severity === "high") return "var(--td-action-avoid)";
  if (severity === "watch") return "var(--td-action-breakout-watch)";
  return "var(--td-ink-500)";
}

function UnusualFlowPanel({
  flags,
  error,
  note,
  nScanned,
  asof,
}: {
  flags: UnusualOptionsFlag[];
  error?: string | null;
  note?: string | null;
  nScanned?: number;
  asof?: string | null;
}) {
  return (
    <section className="td-panel flex flex-col gap-3 p-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <span className="td-label">Unusual options flow · same day</span>
          <p className="text-[12px]" style={{ color: "var(--td-ink-500)" }}>
            Chain volume / OI / premium pressure (not OPRA prints). Flags contracts that look
            unusually active vs open interest or size.
          </p>
        </div>
        <Chip
          label={
            flags.length > 0
              ? `${flags.length} flag${flags.length === 1 ? "" : "s"}`
              : "no flags"
          }
          colorVar={
            flags.length > 0
              ? colorVarFor("mode", "WAIT")
              : colorVarFor("mode", "STAND_ASIDE")
          }
        />
      </div>

      {error ? (
        <p className="text-[12px]" style={{ color: "var(--td-action-breakout-watch)" }}>
          Flow scanner partial: {error.slice(0, 180)}
        </p>
      ) : null}

      {flags.length === 0 && !error ? (
        <p className="text-[13px]" style={{ color: "var(--td-ink-400)" }}>
          No unusual flow on the latest chain snapshot
          {nScanned != null ? ` (${nScanned} contracts scanned)` : ""}.
        </p>
      ) : null}

      {flags.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[12px]">
            <thead>
              <tr style={{ color: "var(--td-ink-500)" }}>
                <th className="py-1 pr-3 font-medium">Contract</th>
                <th className="py-1 pr-3 font-medium">Vol / OI</th>
                <th className="py-1 pr-3 font-medium">Premium</th>
                <th className="py-1 pr-3 font-medium">Score</th>
                <th className="py-1 font-medium">Why unusual</th>
              </tr>
            </thead>
            <tbody>
              {flags.map((f) => {
                const key = `${f.expiry}-${f.right}-${f.strike}-${f.score}`;
                const border = severityColor(f.severity);
                return (
                  <tr
                    key={key}
                    style={{
                      color: "var(--td-ink-100)",
                      borderTop: "1px solid var(--td-line)",
                    }}
                  >
                    <td
                      className="py-1.5 pr-3 tabular"
                      style={{ fontFamily: "var(--td-font-mono)" }}
                    >
                      <span style={{ color: border, fontWeight: 600 }}>
                        {f.right}
                        {formatNum(f.strike)}
                      </span>{" "}
                      <span style={{ color: "var(--td-ink-500)" }}>
                        {f.expiry}
                        {f.dte != null ? ` · ${f.dte}d` : ""}
                      </span>
                    </td>
                    <td className="py-1.5 pr-3 tabular">
                      {formatNum(f.volume, 0)}
                      {f.open_interest != null
                        ? ` / ${formatNum(f.open_interest, 0)}`
                        : ""}
                      {f.vol_oi != null ? (
                        <span style={{ color: "var(--td-ink-500)" }}>
                          {" "}
                          ({formatNum(f.vol_oi, 1)}x)
                        </span>
                      ) : null}
                    </td>
                    <td className="py-1.5 pr-3 tabular">
                      {f.premium != null ? formatUsd(f.premium, 0) : "—"}
                    </td>
                    <td
                      className="py-1.5 pr-3 tabular"
                      style={{ color: border, fontFamily: "var(--td-font-mono)" }}
                    >
                      {formatNum(f.score, 1)}
                    </td>
                    <td className="py-1.5" style={{ color: "var(--td-ink-400)" }}>
                      {f.reason || (f.reasons ?? []).slice(0, 3).join(" · ")}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}

      <p className="text-[11px]" style={{ color: "var(--td-ink-500)" }}>
        {note ||
          "Proxy from listed chain aggregates — not multi-exchange sweeps or dark-pool tape."}
        {asof ? ` · as-of ${asof}` : ""}
      </p>
    </section>
  );
}

function OptionsDeskInner({ showHeader = true }: { showHeader?: boolean }) {
  const searchParams = useSearchParams();
  const qSymbol = searchParams.get("symbol")?.toUpperCase() ?? "";
  const qAccount = Number(searchParams.get("account") || "1000");

  const [symbol, setSymbol] = useState(qSymbol || "APLD");
  const [account, setAccount] = useState(
    Number.isFinite(qAccount) && qAccount > 0 ? qAccount : 1000,
  );
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
    // Deep-link or default symbol — always pull the live chain so the board is not empty.
    void run(qSymbol || symbol);
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
        description="Unusual same-day flow flags + defined-risk structure ticket. Flow is chain-proxy research; never auto-trades."
        actions={
          symbol ? (
            <div className="flex flex-wrap gap-2">
              <Link
                href={analyzeHref({ symbol })}
                className="td-btn td-btn-ghost no-underline"
              >
                Analyze
              </Link>
              <Link href={liveHref(symbol, "ticket", account)} className="td-btn td-btn-ghost no-underline">
                Live
              </Link>
              <Link href={liveHref(symbol, "gamma", account)} className="td-btn td-btn-ghost no-underline">
                Gamma
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
            {loading ? "Loading live feed…" : "Load live options feed"}
          </button>
        </div>
        <p className="text-[11px]" style={{ color: "var(--td-ink-500)" }}>
          Pulls the live chain + risk mode + a defined-risk structure. Prefer APLD / IONQ on small
          books · avoid MU ATM weeklies · default bull call debit spread 14–45 DTE
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
            title="No live options feed yet"
            steps={[
              "Enter a symbol (start with APLD or IONQ)",
              "Press Load live options feed",
              "Read risk mode + structure — only size when mode is OPTIONS_ATTACK and structure is buy",
            ]}
          />
        </section>
      ) : null}

      {plan ? (
        <UnusualFlowPanel
          flags={plan.unusual_flow?.flags ?? plan.unusual_flow?.unusual ?? []}
          error={plan.unusual_flow_error ?? plan.unusual_flow?.error}
          note={plan.unusual_flow?.methodology_note}
          nScanned={plan.unusual_flow?.n_scanned}
          asof={plan.unusual_flow?.asof_utc ?? plan.asof_utc}
        />
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
                value={
                  plan.live?.go_long == null
                    ? "—"
                    : plan.live.go_long
                      ? "yes"
                      : "no"
                }
              />
              <Stat
                label="Risk budget"
                value={
                  structure?.budget != null
                    ? formatUsd(structure.budget, 0)
                    : formatUsd((plan.account ?? account) * (riskPct / 100), 0)
                }
              />
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
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-2">
                  <Stat
                    label="Expiry (chain)"
                    value={
                      structure?.expiry
                        ? `${structure.expiry}${structure.dte != null ? ` · ${structure.dte}d` : ""}`
                        : "—"
                    }
                    emphasize
                  />
                  <Stat
                    label="Max loss / 1"
                    value={formatUsd(structure?.max_loss_1_contract, 0)}
                    emphasize
                  />
                  <Stat label="Long strike" value={structure?.long_strike != null ? formatNum(structure.long_strike) : "—"} />
                  <Stat
                    label="Short strike"
                    value={
                      structure?.short_strike != null
                        ? formatNum(structure.short_strike)
                        : "—"
                    }
                  />
                  <Stat label="Debit / sh" value={formatUsd(structure?.debit_per_share)} />
                  <Stat
                    label="Contracts fit"
                    value={
                      structure?.contracts != null
                        ? String(structure.contracts)
                        : structure?.budget != null &&
                            structure?.max_loss_1_contract != null &&
                            structure.max_loss_1_contract > 0
                          ? String(
                              Math.max(
                                0,
                                Math.floor(
                                  structure.budget / structure.max_loss_1_contract,
                                ),
                              ),
                            )
                          : "—"
                    }
                  />
                  <Stat label="Long Δ" value={formatNum(structure?.long_delta, 2)} />
                  <Stat
                    label="Long IV"
                    value={
                      structure?.iv_long != null
                        ? `${(structure.iv_long * 100).toFixed(0)}%`
                        : "—"
                    }
                  />
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
        <section className="td-panel flex flex-col gap-3 p-5">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <span className="td-label">Live options insights · research only</span>
              <p className="text-[12px]" style={{ color: "var(--td-ink-500)" }}>
                Live chain flow + ATM IV vs realized vol. Warnings only — never sets OPTIONS_ATTACK alone.
              </p>
            </div>
            {plan.vol_package?.recommended ? (
              <Chip
                label={`${plan.vol_package.recommended.template} · ${plan.vol_package.recommended.action}`}
                colorVar={
                  plan.vol_package.recommended.action === "consider"
                    ? colorVarFor("mode", "WAIT")
                    : colorVarFor("mode", "STAND_ASIDE")
                }
              />
            ) : null}
          </div>

          {plan.vol_package_error ? (
            <p className="text-[12px]" style={{ color: "var(--td-action-breakout-watch)" }}>
              Vol scorer partial: {plan.vol_package_error.slice(0, 180)}
            </p>
          ) : null}

          {(plan.vol_package?.warnings ?? []).length > 0 ? (
            <div className="flex flex-col gap-2">
              {(plan.vol_package?.warnings ?? []).map((w) => {
                const border =
                  w.severity === "danger"
                    ? "var(--td-action-avoid)"
                    : w.severity === "watch"
                      ? "var(--td-action-breakout-watch)"
                      : "var(--td-line)";
                const bg =
                  w.severity === "danger"
                    ? "color-mix(in srgb, var(--td-action-avoid) 12%, transparent)"
                    : w.severity === "watch"
                      ? "color-mix(in srgb, var(--td-action-breakout-watch) 10%, transparent)"
                      : "transparent";
                return (
                  <div
                    key={`${w.code}-${w.message.slice(0, 24)}`}
                    className="rounded px-3 py-2 text-[13px] leading-snug"
                    style={{
                      borderLeft: `3px solid ${border}`,
                      background: bg,
                      color: "var(--td-ink-100)",
                    }}
                    role={w.severity === "danger" ? "alert" : "status"}
                  >
                    <span
                      className="mr-2 text-[10px] font-semibold uppercase tracking-wide"
                      style={{
                        color: border,
                        fontFamily: "var(--td-font-mono)",
                      }}
                    >
                      {w.severity}
                    </span>
                    {w.message}
                  </div>
                );
              })}
            </div>
          ) : null}

          {plan.vol_package?.features ? (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat
                label="ATM IV"
                value={
                  plan.vol_package.features.atm_iv != null &&
                  Number.isFinite(plan.vol_package.features.atm_iv)
                    ? `${(plan.vol_package.features.atm_iv * 100).toFixed(1)}%`
                    : "—"
                }
              />
              <Stat
                label="Realized vol"
                value={
                  plan.vol_package.features.rv_har_ann != null &&
                  Number.isFinite(plan.vol_package.features.rv_har_ann)
                    ? `${(plan.vol_package.features.rv_har_ann * 100).toFixed(1)}%`
                    : "—"
                }
              />
              <Stat
                label="IV vs RV"
                value={
                  plan.vol_package.features.iv_rv_spread != null &&
                  Number.isFinite(plan.vol_package.features.iv_rv_spread)
                    ? `${plan.vol_package.features.iv_rv_spread > 0 ? "rich +" : "cheap "}${(Math.abs(plan.vol_package.features.iv_rv_spread) * 100).toFixed(1)} pts`
                    : "—"
                }
              />
              <Stat
                label="Spot 5d"
                value={
                  plan.vol_package.features.spot_ret_5d != null &&
                  Number.isFinite(plan.vol_package.features.spot_ret_5d)
                    ? `${plan.vol_package.features.spot_ret_5d >= 0 ? "+" : ""}${(plan.vol_package.features.spot_ret_5d * 100).toFixed(1)}%`
                    : "—"
                }
              />
              <Stat
                label="Put/Call vol"
                value={
                  plan.vol_package.features.put_call_vol_ratio != null &&
                  Number.isFinite(plan.vol_package.features.put_call_vol_ratio)
                    ? `${plan.vol_package.features.put_call_vol_ratio.toFixed(2)}x`
                    : "—"
                }
              />
              <Stat
                label="Put/Call OI"
                value={
                  plan.vol_package.features.put_call_oi_ratio != null &&
                  Number.isFinite(plan.vol_package.features.put_call_oi_ratio)
                    ? `${plan.vol_package.features.put_call_oi_ratio.toFixed(2)}x`
                    : "—"
                }
              />
              <Stat
                label="Put vol"
                value={
                  plan.vol_package.features.put_volume != null
                    ? formatNum(plan.vol_package.features.put_volume, 0)
                    : "—"
                }
              />
              <Stat
                label="Call vol"
                value={
                  plan.vol_package.features.call_volume != null
                    ? formatNum(plan.vol_package.features.call_volume, 0)
                    : "—"
                }
              />
            </div>
          ) : !plan.vol_package_error ? (
            <p className="text-[13px]" style={{ color: "var(--td-ink-400)" }}>
              No live chain insights yet.
            </p>
          ) : null}

          {(plan.vol_package?.packages ?? []).length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-[12px]">
                <thead>
                  <tr style={{ color: "var(--td-ink-500)" }}>
                    <th className="py-1 pr-3 font-medium">Template</th>
                    <th className="py-1 pr-3 font-medium">Action</th>
                    <th className="py-1 pr-3 font-medium">Score</th>
                    <th className="py-1 pr-3 font-medium">Edge−cost</th>
                    <th className="py-1 font-medium">Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {(plan.vol_package?.packages ?? []).map((pkg) => (
                    <tr
                      key={pkg.template}
                      style={{
                        color:
                          pkg.action === "consider"
                            ? "var(--td-ink-100)"
                            : "var(--td-ink-300)",
                        borderTop: "1px solid var(--td-line)",
                      }}
                    >
                      <td
                        className="py-1.5 pr-3 tabular"
                        style={{ fontFamily: "var(--td-font-mono)" }}
                      >
                        {pkg.template}
                      </td>
                      <td className="py-1.5 pr-3">{pkg.action}</td>
                      <td className="py-1.5 pr-3 tabular">
                        {formatNum(pkg.score, 2)}
                      </td>
                      <td className="py-1.5 pr-3 tabular">
                        {formatNum(pkg.edge_after_cost_proxy ?? null, 3)}
                      </td>
                      <td className="py-1.5" style={{ color: "var(--td-ink-500)" }}>
                        {(pkg.reasons ?? []).slice(0, 2).join(" · ")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </section>
      ) : null}

      {plan ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <section className="td-panel p-4">
            <h2
              className="mb-2 text-[14px] font-medium"
              style={{ color: "var(--td-ink-100)" }}
            >
              Operator rules
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
              Preferred names: {plan.playbook.preferred.join(", ")} · Avoid ATM weeklies:{" "}
              {plan.playbook.avoid_atm.join(", ") || "—"}
            </p>
          </section>

          <section className="td-panel p-4">
            <h2
              className="mb-2 text-[14px] font-medium"
              style={{ color: "var(--td-ink-100)" }}
            >
              How this ticket is built
            </h2>
            <p className="text-[13px] leading-snug" style={{ color: "var(--td-ink-300)" }}>
              {plan.research.note}
            </p>
            <p className="mt-2 text-[12px]" style={{ color: "var(--td-ink-400)" }}>
              OPTIONS_WINNER:{" "}
              <strong style={{ color: "var(--td-ink-200)" }}>
                {plan.research.options_winner ?? "v35_softstruct_bag8"}
              </strong>
              {" · "}
              robust:{" "}
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
