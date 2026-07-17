"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useState, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { Activity, Clock3, ShieldCheck } from "lucide-react";
import type {
  ApiEnvelope,
  OptionsBookRow,
  OptionsBookScanResponse,
  OptionsPlanResponse,
  UnusualOptionsFlag,
} from "@/lib/types";
import { formatNum, formatPct, formatUsd, sanitizeSymbol } from "@/lib/format";
import { PageHeader } from "@/components/shell/PageHeader";
import { analyzeHref, liveHref } from "@/lib/routes";
import { Chip } from "@/components/ui/Chip";
import { Stat } from "@/components/ui/Stat";
import { colorVarFor } from "@/lib/actionColors";

const QUICK_BOOK = ["MSTR", "TSLA", "SKHY", "IONQ"] as const;

function confColor(label: string | undefined): string {
  const u = (label || "").toUpperCase();
  if (u === "HIGH") return colorVarFor("mode", "OPTIONS_ATTACK");
  if (u === "MEDIUM") return colorVarFor("mode", "WAIT");
  if (u === "LOW") return colorVarFor("mode", "STAND_ASIDE");
  return colorVarFor("mode", "STAND_ASIDE");
}

function BookBoard({
  book,
  loading,
  error,
  activeSymbol,
  onSelect,
  onRefresh,
}: {
  book: OptionsBookScanResponse | null;
  loading: boolean;
  error: string | null;
  activeSymbol: string;
  onSelect: (sym: string) => void;
  onRefresh: () => void;
}) {
  const rows: OptionsBookRow[] = book?.rows ?? [];
  return (
    <section className="td-panel flex flex-col gap-3 p-5">
      <div className="flex flex-wrap items-start justify-between gap-2 border-b border-[var(--td-hairline)] pb-3">
        <div>
          <span className="td-label uppercase tracking-wider text-[11px] font-semibold text-[var(--td-ink-100)]">Best options setups</span>
          <p className="text-[12px] text-[var(--td-muted)] mt-1">
            Ranked by price structure, option cost, and market activity.
          </p>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="td-btn td-btn-ghost"
        >
          {loading ? "Scanning book…" : "Scan book"}
        </button>
      </div>

      {error ? (
        <p className="text-[12px] text-[var(--td-action-avoid)]" role="alert">
          Book scan: {error.slice(0, 200)}
        </p>
      ) : null}

      {!book && !loading ? (
        <p className="text-[13px]" style={{ color: "var(--td-ink-400)" }}>
          Press Scan book for a ranked multi-name options read.
        </p>
      ) : null}

      {loading && !book ? (
        <p className="text-[13px] td-muted">Scanning chains for MSTR / TSLA / SKHY / IONQ…</p>
      ) : null}

      {rows.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[12px] border-collapse">
            <thead>
              <tr className="border-b border-[var(--td-hairline)]" style={{ color: "var(--td-ink-400)" }}>
                <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px]">Symbol</th>
                <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px]">Conf</th>
                <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px]">Structure</th>
                <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px] text-right">Max loss</th>
                <th className="py-2 pr-3 font-semibold uppercase tracking-wider text-[10px]">Flow</th>
                <th className="py-2 font-semibold uppercase tracking-wider text-[10px]">Read</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const conf = row.confidence_read;
                const st = row.structure;
                const active = row.symbol === activeSymbol;
                return (
                  <tr
                    key={row.symbol}
                    className="cursor-pointer hover:bg-[var(--td-surface-soft)] transition-colors"
                    style={{
                      borderBottom: "1px solid var(--td-hairline)",
                      background: active
                        ? "color-mix(in srgb, var(--td-brand) 8%, transparent)"
                        : undefined,
                    }}
                    onClick={() => onSelect(row.symbol)}
                  >
                    <td className="py-2.5 pr-3 font-mono font-bold text-[var(--td-ink)]">
                      {row.symbol}
                      {book?.best === row.symbol ? (
                        <span className="ml-1.5 text-[10px] text-[var(--td-brand)] font-semibold">
                          BEST
                        </span>
                      ) : null}
                    </td>
                    <td className="py-2.5 pr-3">
                      <Chip
                        label={`${conf?.label ?? "—"} ${conf?.score != null ? conf.score.toFixed(2) : ""}`.trim()}
                        colorVar={confColor(conf?.label)}
                      />
                    </td>
                    <td className="py-2.5 pr-3" style={{ color: "var(--td-ink-200)" }}>
                      {st?.action === "buy"
                        ? `${st.structure ?? "structure"} · ${st.expiry ?? "—"}`
                        : st?.reason || st?.error || row.error || "skip"}
                    </td>
                    <td className="py-2.5 pr-3 font-mono text-right">
                      {st?.action === "buy" ? formatUsd(st.max_loss_1_contract, 0) : "—"}
                    </td>
                    <td className="py-2.5 pr-3 font-mono" style={{ color: "var(--td-ink-300)" }}>
                      {row.unusual_flow?.bias ?? "—"}
                      {row.unusual_flow?.n_flagged != null
                        ? ` · ${row.unusual_flow.n_flagged}f`
                        : ""}
                    </td>
                    <td className="py-2.5 text-[11px]" style={{ color: "var(--td-ink-400)" }}>
                      {(conf?.reasons ?? []).slice(0, 1).join("") || conf?.stance || "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}

      {book?.note ? (
        <p className="text-[11px]" style={{ color: "var(--td-ink-500)" }}>
          {book.note}
        </p>
      ) : null}
    </section>
  );
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
  const [selectedExpiry, setSelectedExpiry] = useState("all");

  const listedExpiries = useMemo(() => {
    const dates = new Set(flags.map(f => f.expiry).filter(Boolean));
    return Array.from(dates).sort();
  }, [flags]);

  const filteredFlags = useMemo(() => {
    if (selectedExpiry === "all") return flags;
    return flags.filter(f => f.expiry === selectedExpiry);
  }, [flags, selectedExpiry]);

  // Compute flow summary metrics based on filtered flags
  const callFlags = filteredFlags.filter(f => f.right === "C" || f.right?.toUpperCase() === "CALL");
  const putFlags = filteredFlags.filter(f => f.right === "P" || f.right?.toUpperCase() === "PUT");
  const totalPremium = filteredFlags.reduce((acc, f) => acc + (f.premium || 0), 0);
  const totalVolume = filteredFlags.reduce((acc, f) => acc + (f.volume || 0), 0);

  let sentimentImplication = "Neutral / Balanced Flow";
  let sentimentColorClass = "text-[var(--td-muted)] bg-[var(--td-surface-elevated)]";
  if (callFlags.length > putFlags.length * 1.5) {
    sentimentImplication = "Strong Bullish Speculative Activity (Call Buying Dominant)";
    sentimentColorClass = "text-[#8fc39d] bg-[#2F6B4F1A] border border-[#2F6B4F33]";
  } else if (callFlags.length > putFlags.length) {
    sentimentImplication = "Moderately Bullish Flow";
    sentimentColorClass = "text-[#8fc39d] bg-[#2F6B4F0A]";
  } else if (putFlags.length > callFlags.length * 1.5) {
    sentimentImplication = "Strong Bearish Bias / Downside Hedging (Put Buying Dominant)";
    sentimentColorClass = "text-[#dc7e76] bg-[#A348481A] border border-[#A3484833]";
  } else if (putFlags.length > callFlags.length) {
    sentimentImplication = "Moderately Bearish Flow";
    sentimentColorClass = "text-[#dc7e76] bg-[#A348480A]";
  }

  return (
    <section className="td-panel flex flex-col gap-4 p-5">
      <div className="flex flex-wrap items-start justify-between gap-2 border-b border-[var(--td-hairline)] pb-3">
        <div>
          <span className="td-label uppercase tracking-wider text-[11px] font-semibold text-[var(--td-ink-100)]">
            Unusual Options Flow · Chain-Proxy Monitor
          </span>
          <p className="text-[12px] text-[var(--td-muted)] mt-1">
            Detects same-day contracts with abnormal volume, open interest ratios, or aggressive premium spikes.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {listedExpiries.length > 0 && (
            <label className="flex items-center gap-2 text-[12px] text-[var(--td-muted)]">
              <span>Expiry Filter:</span>
              <select
                value={selectedExpiry}
                onChange={(e) => setSelectedExpiry(e.target.value)}
                className="td-input py-1 px-2 text-[12px]"
                style={{ fontFamily: "var(--td-font-mono)", background: "var(--td-surface-soft)" }}
              >
                <option value="all">All Expirations</option>
                {listedExpiries.map((d) => (
                  <option key={`opt-expiry-${d}`} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </label>
          )}
          <Chip
            label={
              filteredFlags.length > 0
                ? `${filteredFlags.length} flag${filteredFlags.length === 1 ? "" : "s"} detected`
                : "no active flags"
            }
            colorVar={
              filteredFlags.length > 0
                ? colorVarFor("mode", "WAIT")
                : colorVarFor("mode", "STAND_ASIDE")
            }
          />
        </div>
      </div>

      {error ? (
        <div className="text-[12px] text-[var(--td-action-avoid)] bg-[var(--td-action-avoid-soft)] p-2.5 rounded border border-[var(--td-action-avoid)]">
          Flow scanner partial: {error.slice(0, 180)}
        </div>
      ) : null}

      {filteredFlags.length === 0 && !error ? (
        <p className="text-[13px]" style={{ color: "var(--td-ink-400)" }}>
          No unusual flow matches filter
          {nScanned != null ? ` (${nScanned} contracts scanned)` : ""}.
        </p>
      ) : null}

      {filteredFlags.length > 0 ? (
        <>
          {/* Sentiment Summary Card */}
          <div className={`p-3.5 rounded-lg flex flex-col md:flex-row md:items-center justify-between gap-3 ${sentimentColorClass}`}>
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-current animate-pulse shrink-0" />
              <div className="flex flex-col">
                <span className="text-[10px] uppercase font-bold tracking-wider opacity-85">Net Flow Implication</span>
                <strong className="text-sm font-semibold">{sentimentImplication}</strong>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[11px] opacity-90">
              <div>Calls: <strong className="font-bold">{callFlags.length}</strong></div>
              <div className="text-[var(--td-hairline)] md:block hidden">|</div>
              <div>Puts: <strong className="font-bold">{putFlags.length}</strong></div>
              <div className="text-[var(--td-hairline)] md:block hidden">|</div>
              <div>Vol: <strong className="font-bold">{formatNum(totalVolume, 0)}</strong></div>
              <div className="text-[var(--td-hairline)] md:block hidden">|</div>
              <div>Premium: <strong className="font-bold">{formatUsd(totalPremium, 0)}</strong></div>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-[12px] border-collapse">
              <thead>
                <tr className="border-b border-[var(--td-hairline)]" style={{ color: "var(--td-ink-400)" }}>
                  <th className="py-2.5 pr-3 font-semibold uppercase tracking-wider text-[10px]">Ticker</th>
                  <th className="py-2.5 pr-3 font-semibold uppercase tracking-wider text-[10px]">Type</th>
                  <th className="py-2.5 pr-3 font-semibold uppercase tracking-wider text-[10px] text-right">Strike</th>
                  <th className="py-2.5 pr-3 font-semibold uppercase tracking-wider text-[10px]">Expiry / DTE</th>
                  <th className="py-2.5 pr-3 font-semibold uppercase tracking-wider text-[10px] text-right">Volume</th>
                  <th className="py-2.5 pr-3 font-semibold uppercase tracking-wider text-[10px] text-right">Premium</th>
                  <th className="py-2.5 pr-3 font-semibold uppercase tracking-wider text-[10px] text-right">Vol / OI</th>
                  <th className="py-2.5 pr-3 font-semibold uppercase tracking-wider text-[10px] text-center">Sentiment Bias</th>
                  <th className="py-2.5 font-semibold uppercase tracking-wider text-[10px] pl-2">Why Flagged</th>
                </tr>
              </thead>
              <tbody>
                {filteredFlags.map((f, i) => {
                  const key = `${f.symbol}-${f.expiry}-${f.right}-${f.strike}-${i}`;
                  const isCall = f.right === "C" || f.right?.toUpperCase() === "CALL";
                  return (
                    <tr
                      key={key}
                      className="hover:bg-[var(--td-surface-soft)] transition-colors"
                      style={{
                        color: "var(--td-ink-100)",
                        borderBottom: "1px solid var(--td-hairline)",
                      }}
                    >
                      {/* Ticker */}
                      <td className="py-2.5 pr-3 font-mono font-bold text-[var(--td-ink)]">
                        {f.symbol || "—"}
                      </td>

                      {/* Type (Call / Put) */}
                      <td className="py-2.5 pr-3">
                        <span className={`px-1.5 py-0.5 rounded font-mono text-[10px] font-bold ${
                          isCall
                            ? "bg-[#2F6B4F1A] text-[#8fc39d]"
                            : "bg-[#A348481A] text-[#dc7e76]"
                        }`}>
                          {isCall ? "CALL" : "PUT"}
                        </span>
                      </td>

                      {/* Strike */}
                      <td className="py-2.5 pr-3 font-mono font-semibold text-right text-[13px] text-[var(--td-ink)]">
                        {formatUsd(f.strike)}
                      </td>

                      {/* Expiry / DTE */}
                      <td className="py-2.5 pr-3">
                        <span className="font-semibold font-mono text-[var(--td-ink)] mr-1.5">{f.dte}d</span>
                        <span className="text-[11px] text-[var(--td-muted)]">({f.expiry})</span>
                      </td>

                      {/* Volume */}
                      <td className="py-2.5 pr-3 font-mono font-bold text-right text-[13px] text-[var(--td-ink)]">
                        {formatNum(f.volume, 0)}
                      </td>

                      {/* Premium */}
                      <td className="py-2.5 pr-3 font-mono text-right text-[var(--td-ink)]">
                        {f.premium != null ? formatUsd(f.premium, 0) : "—"}
                      </td>

                      {/* Vol / OI */}
                      <td className="py-2.5 pr-3 font-mono text-right text-[var(--td-body)]">
                        <span className="font-semibold">{formatNum(f.vol_oi ?? 0, 1)}x</span>
                        {f.open_interest != null && (
                          <span className="text-[10px] text-[var(--td-muted)] ml-1">
                            (OI {formatNum(f.open_interest, 0)})
                          </span>
                        )}
                      </td>

                      {/* Sentiment Bias */}
                      <td className="py-2.5 pr-3 text-center">
                        <span className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
                          isCall
                            ? "bg-[#2F6B4F1A] text-[#8fc39d]"
                            : "bg-[#A348481A] text-[#dc7e76]"
                        }`}>
                          {isCall ? "Bullish Spec / Hedge" : "Bearish Spec / Hedge"}
                        </span>
                      </td>

                      {/* Why Flagged */}
                      <td className="py-2.5 text-[11px] text-[var(--td-body)] max-w-xs truncate pl-2" title={f.reason || (f.reasons ?? []).join(" · ")}>
                        {f.reason || (f.reasons ?? []).slice(0, 3).join(" · ")}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      ) : null}

      <div className="flex justify-between items-center text-[11px] text-[var(--td-muted)] mt-2">
        <span>{note || "Proxy from listed chain aggregates — not multi-exchange sweeps or dark-pool tape."}</span>
        {asof ? <span>As-of {asof}</span> : null}
      </div>
    </section>
  );
}

function OptionsVisualGuide({
  symbol,
  loading,
  ready,
  structure,
  budget,
  maxLoss,
  dte,
  impliedVol,
}: {
  symbol: string;
  loading: boolean;
  ready: boolean;
  structure?: string | null;
  budget?: number | null;
  maxLoss?: number | null;
  dte?: number | null;
  impliedVol?: number | null;
}) {
  const volPercent = impliedVol != null && Number.isFinite(impliedVol)
    ? Math.max(8, Math.min(96, impliedVol * 100))
    : 58;

  return (
    <section className={`options-visual${loading ? " is-loading" : ""}`} aria-label="Options risk overview">
      <div className="options-visual__payoff">
        <header>
          <div><span>{symbol || "SYMBOL"} · PAYOFF SHAPE</span><strong>{structure || "Defined-risk spread"}</strong></div>
          <b className={ready ? "is-ready" : ""}>{loading ? "CHECKING" : ready ? "READY" : "PREVIEW"}</b>
        </header>
        <svg viewBox="0 0 620 250" role="img" aria-label="Limited loss and limited gain payoff diagram">
          <line x1="30" y1="178" x2="590" y2="178" className="axis" />
          <line x1="280" y1="26" x2="280" y2="220" className="strike" />
          <path d="M30 207 L280 207 L430 66 L590 66" className="payoff" />
          <path d="M30 207 L280 207 L430 66 L590 66 L590 178 L30 178 Z" className="payoff-fill" />
          <text x="36" y="235">LOSS IS CAPPED</text>
          <text x="448" y="46">PROFIT IS CAPPED</text>
          <text x="292" y="168">BREAKEVEN</text>
        </svg>
        <div className="options-visual__legend"><span><i className="is-loss" /> Loss area</span><span><i className="is-profit" /> Profit area</span><small>Illustrative until a live chain loads</small></div>
      </div>

      <div className="options-visual__facts">
        <article>
          <ShieldCheck size={17} />
          <span>MOST YOU RISK</span>
          <strong>{maxLoss != null ? formatUsd(maxLoss, 0) : budget != null ? `Up to ${formatUsd(budget, 0)}` : "Set by budget"}</strong>
          <small>Known before the paper plan</small>
        </article>
        <article>
          <Clock3 size={17} />
          <span>TIME WINDOW</span>
          <strong>{dte != null ? `${dte} days` : "14–45 days"}</strong>
          <small>Avoids same-week guessing</small>
        </article>
        <article className="options-visual__vol">
          <Activity size={17} />
          <span>OPTION COST</span>
          <strong>{impliedVol != null ? `${(impliedVol * 100).toFixed(0)}% volatility` : "Checking volatility"}</strong>
          <div><i style={{ width: `${volPercent}%` }} /></div>
          <small>Higher means options are pricier</small>
        </article>
      </div>
    </section>
  );
}

function OptionsDeskInner({ showHeader = true }: { showHeader?: boolean }) {
  const searchParams = useSearchParams();
  const qSymbol = sanitizeSymbol(searchParams.get("symbol") ?? "") ?? "";
  const qAccount = Number(searchParams.get("account") || "1000");

  const [symbol, setSymbol] = useState(qSymbol || "IONQ");
  const [account, setAccount] = useState(
    Number.isFinite(qAccount) && qAccount > 0 ? qAccount : 1000,
  );
  const [riskPct, setRiskPct] = useState(18);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [plan, setPlan] = useState<OptionsPlanResponse | null>(null);
  const [book, setBook] = useState<OptionsBookScanResponse | null>(null);
  const [bookLoading, setBookLoading] = useState(false);
  const [bookError, setBookError] = useState<string | null>(null);

  useEffect(() => {
    if (qSymbol) setSymbol(qSymbol);
  }, [qSymbol]);

  const run = useCallback(
    async (symOverride?: string) => {
      const raw = (symOverride ?? symbol).trim();
      const sym = sanitizeSymbol(raw) ?? raw.toUpperCase().replace(/[^A-Z0-9]/g, "");
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

  const runBook = useCallback(async () => {
    setBookLoading(true);
    setBookError(null);
    try {
      const res = await fetch("/api/options-book", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbols: QUICK_BOOK.join(","),
          account,
          risk_pct: riskPct,
          workers: 4,
        }),
      });
      const json = (await res.json()) as ApiEnvelope<OptionsBookScanResponse>;
      if (!res.ok || json.ok === false || !json.data) {
        throw new Error(json.error ?? `options-book failed (${res.status})`);
      }
      setBook(json.data);
      // Auto-focus best name when no deep-link symbol
      if (!qSymbol && json.data.best) {
        void run(json.data.best);
      }
    } catch (e) {
      setBookError(e instanceof Error ? e.message : "options book scan failed");
    } finally {
      setBookLoading(false);
    }
  }, [account, riskPct, qSymbol, run]);

  useEffect(() => {
    // Deep-link or default symbol — always pull the live chain so the board is not empty.
    void run(qSymbol || symbol);
    void runBook();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qSymbol]);

  const structure = plan?.structure;
  const isBuy = structure?.action === "buy";
  const attack =
    plan?.mode?.toUpperCase().includes("OPTIONS") === true && isBuy;
  const modelId = plan?.model?.model ?? null;
  const confState = plan?.confidence?.state ?? null;
  const confProb =
    plan?.confidence?.calibrated_probability ??
    plan?.model?.confidence ??
    plan?.live?.confidence ??
    null;

  const optionBudget =
    structure?.budget ?? (Number.isFinite(account) ? account * (riskPct / 100) : null);

  const body = (
    <>
      {showHeader && <PageHeader
        title="Options"
        description="Book board + unusual flow + defined-risk structure. Flow is chain-proxy research; never auto-trades."
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
              onKeyDown={(e) => {
                if (e.key === "Enter") void run();
              }}
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
        <div className="flex flex-wrap items-center gap-2 mt-2">
          <span className="text-[11px]" style={{ color: "var(--td-ink-500)" }}>
            Quick:
          </span>
          {QUICK_BOOK.map((s) => (
            <button
              key={s}
              type="button"
              className="td-btn td-btn-ghost"
              style={{
                fontFamily: "var(--td-font-mono)",
                fontSize: 12,
                padding: "4px 10px",
                borderColor:
                  symbol === s ? "var(--td-brand)" : undefined,
              }}
              onClick={() => void run(s)}
              disabled={loading}
            >
              {s}
            </button>
          ))}
          <span className="text-[11px]" style={{ color: "var(--td-ink-500)" }}>
            Defined-risk spreads · only sizes when every safety check passes
          </span>
        </div>
      </section>

      <OptionsVisualGuide
        symbol={symbol}
        loading={loading}
        ready={attack}
        structure={structure?.structure}
        budget={optionBudget}
        maxLoss={structure?.max_loss_1_contract}
        dte={structure?.dte}
        impliedVol={structure?.iv_long}
      />

      {error ? (
        <p className="td-alert td-alert--error" role="alert">
          {error}
        </p>
      ) : null}

      <BookBoard
        book={book}
        loading={bookLoading}
        error={bookError}
        activeSymbol={symbol}
        onSelect={(sym) => void run(sym)}
        onRefresh={() => void runBook()}
      />

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
              <Stat label="Model" value={modelId ?? "—"} />
              <Stat label="Conf gate" value={confState ?? "—"} />
              <Stat
                label="Conf / model"
                value={
                  confProb == null || !Number.isFinite(Number(confProb))
                    ? "—"
                    : formatPct(Number(confProb))
                }
              />
              <Stat
                label="Live src"
                value={plan.live?.source ?? "—"}
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
