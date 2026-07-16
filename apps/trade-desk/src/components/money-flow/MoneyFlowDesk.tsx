"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { analyzeHref } from "@/lib/routes";

/* ─── Types matching tools/sector_money_flow.py ─── */

export type SectorFlowRow = {
  etf: string;
  name?: string;
  sector?: string;
  bucket?: string;
  ret_1d?: number | null;
  ret_5d?: number | null;
  ret_21d?: number | null;
  rs_1d?: number | null;
  rs_5d?: number | null;
  rs_21d?: number | null;
  flow_score?: number | null;
  flow_direction?: "in" | "out" | "neutral" | string;
  definitive?: boolean;
  definitive_score?: number | null;
  definitive_reasons?: string[];
  above_ma20?: boolean | null;
  rvol?: number | null;
  rank?: number;
  focus_names?: string[];
  names?: string[];
};

export type ThemeRotation = {
  id?: string;
  label?: string;
  from_etf?: string;
  to_etf?: string;
  summary?: string;
  magnitude?: number | null;
  definitive?: boolean;
};

export type RotationBlock = {
  kind?: string;
  summary?: string;
  is_definitive?: boolean;
  confidence?: number | null;
  money_in_etfs?: string[];
  money_out_etfs?: string[];
  xly_xlp_5d?: number | null;
  xlk_xlp_5d?: number | null;
  semis_vs_tech_1d?: number | null;
  theme_rotations?: ThemeRotation[];
};

export type MarketContext = {
  benchmark?: string;
  spy_ret_1d?: number | null;
  spy_ret_5d?: number | null;
  spy_ret_21d?: number | null;
  spy_above_ma20?: boolean | null;
  qqq_ret_5d?: number | null;
  qqq_spy_rs_5d?: number | null;
  soxx_rs_1d?: number | null;
  xlk_rs_1d?: number | null;
  igv_rs_1d?: number | null;
  smh_rs_1d?: number | null;
  ratios?: Record<
    string,
    {
      pair?: string;
      ret_1d?: number | null;
      ret_5d?: number | null;
      ret_21d?: number | null;
    }
  >;
};

export type WatchName = {
  symbol: string;
  sector_hint?: string;
  etf?: string;
  score?: number | null;
  rs_5d?: number | null;
  rs_21d?: number | null;
  parent_definitive?: boolean;
};

export type MoneyFlowReport = {
  ok?: boolean;
  error?: string;
  asof?: string;
  asof_bar?: string | null;
  benchmark?: string;
  source?: string;
  market_context?: MarketContext;
  rotation?: RotationBlock;
  sectors_ranked?: SectorFlowRow[];
  money_in?: SectorFlowRow[];
  money_out?: SectorFlowRow[];
  leaders?: SectorFlowRow[];
  laggards?: SectorFlowRow[];
  trading_notes?: string[];
  narrative?: string[];
  watch_names?: WatchName[];
  disclaimer?: string;
  theme_rotations?: ThemeRotation[];
  missing_themes?: string[];
};

type SourceMode = "auto" | "local" | "yfinance";

/* ─── Format helpers ─── */

function pctSigned(n: number | null | undefined, digits = 1): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const v = n * 100;
  return `${v >= 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

function toneForPct(n: number | null | undefined): "up" | "down" | "flat" {
  if (n == null || !Number.isFinite(n) || Math.abs(n) < 1e-6) return "flat";
  return n > 0 ? "up" : "down";
}

function kindLabel(kind: string | undefined): string {
  switch (kind) {
    case "risk_on":
      return "RISK ON";
    case "defensive":
      return "DEFENSIVE";
    case "broad_risk_off":
      return "RISK OFF";
    case "internal":
      return "INTERNAL";
    case "broad_bid":
      return "BROAD BID";
    case "semis_to_tech":
      return "SEMIS → TECH";
    case "tech_to_semis":
      return "TECH → SEMIS";
    default:
      return (kind || "UNCLEAR").replace(/_/g, " ").toUpperCase();
  }
}

function kindClass(kind: string | undefined): string {
  switch (kind) {
    case "risk_on":
    case "broad_bid":
    case "tech_to_semis":
      return "mf-regime--on";
    case "defensive":
      return "mf-regime--def";
    case "broad_risk_off":
      return "mf-regime--off";
    case "internal":
    case "semis_to_tech":
      return "mf-regime--int";
    default:
      return "mf-regime--unk";
  }
}

function flowBarWidth(score: number | null | undefined, maxAbs: number): number {
  if (score == null || !Number.isFinite(score) || maxAbs <= 0) return 0;
  return Math.min(100, (Math.abs(score) / maxAbs) * 100);
}

function sectorLabel(s: SectorFlowRow): string {
  return s.name || s.sector || s.etf;
}

/* ─── Subcomponents ─── */

function MetricPill({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "up" | "down" | "flat";
}) {
  return (
    <div className="mf-metric">
      <span className="mf-metric__label">{label}</span>
      <span className={`mf-metric__value tabular mf-tone--${tone || "flat"}`}>
        {value}
      </span>
    </div>
  );
}

function DefChip({
  definitive,
  score,
}: {
  definitive?: boolean;
  score?: number | null;
}) {
  const s =
    score != null && Number.isFinite(score)
      ? `${Math.round(score * 100)}`
      : "—";
  return (
    <span
      className={
        definitive ? "mf-def mf-def--yes" : "mf-def mf-def--no"
      }
      title={
        definitive
          ? "Multi-horizon + structure agree"
          : "Horizons or volume disagree — noise risk"
      }
    >
      {definitive ? "DEFINITIVE" : "SOFT"}
      <span className="mf-def__score tabular">{s}</span>
    </span>
  );
}

function DirChip({ dir }: { dir?: string }) {
  const d = dir || "neutral";
  return (
    <span className={`mf-dir mf-dir--${d}`}>
      {d === "in" ? "IN" : d === "out" ? "OUT" : "—"}
    </span>
  );
}

function ConfidenceMeter({ value }: { value: number | null | undefined }) {
  const v =
    value != null && Number.isFinite(value)
      ? Math.max(0, Math.min(1, value))
      : 0;
  return (
    <div className="mf-conf" aria-label={`Confidence ${Math.round(v * 100)}%`}>
      <div className="mf-conf__track">
        <div className="mf-conf__fill" style={{ width: `${v * 100}%` }} />
      </div>
      <span className="mf-conf__num tabular">{Math.round(v * 100)}</span>
    </div>
  );
}

function FlowCard({
  row,
  side,
}: {
  row: SectorFlowRow;
  side: "in" | "out";
}) {
  const names = (row.focus_names || row.names || []).slice(0, 5);
  const reasons = (row.definitive_reasons || []).slice(0, 2);
  return (
    <article className={`mf-card mf-card--${side}`}>
      <header className="mf-card__head">
        <div className="mf-card__id">
          <span className="mf-card__etf">{row.etf}</span>
          <span className="mf-card__name">{sectorLabel(row)}</span>
          {row.bucket ? (
            <span className="mf-card__bucket">{row.bucket}</span>
          ) : null}
        </div>
        <div className="mf-card__chips">
          <DirChip dir={row.flow_direction || side} />
          <DefChip
            definitive={row.definitive}
            score={row.definitive_score}
          />
        </div>
      </header>

      <div className="mf-card__grid">
        <div className="mf-card__stat">
          <span>1d</span>
          <b className={`tabular mf-tone--${toneForPct(row.ret_1d)}`}>
            {pctSigned(row.ret_1d)}
          </b>
        </div>
        <div className="mf-card__stat">
          <span>5d</span>
          <b className={`tabular mf-tone--${toneForPct(row.ret_5d)}`}>
            {pctSigned(row.ret_5d)}
          </b>
        </div>
        <div className="mf-card__stat">
          <span>RS 5d</span>
          <b className={`tabular mf-tone--${toneForPct(row.rs_5d)}`}>
            {pctSigned(row.rs_5d)}
          </b>
        </div>
        <div className="mf-card__stat">
          <span>RS 21d</span>
          <b className={`tabular mf-tone--${toneForPct(row.rs_21d)}`}>
            {pctSigned(row.rs_21d)}
          </b>
        </div>
      </div>

      <div className="mf-card__meta">
        <span>
          MA20{" "}
          {row.above_ma20 == null
            ? "—"
            : row.above_ma20
              ? "above"
              : "below"}
        </span>
        <span>
          rvol{" "}
          <span className="tabular">
            {row.rvol != null && Number.isFinite(row.rvol)
              ? `${row.rvol.toFixed(2)}×`
              : "—"}
          </span>
        </span>
      </div>

      {reasons.length ? (
        <ul className="mf-card__reasons">
          {reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      ) : null}

      {names.length ? (
        <div className="mf-card__names">
          {names.map((n) => (
            <Link
              key={n}
              href={analyzeHref({ symbol: n })}
              className="mf-name-chip"
            >
              {n}
            </Link>
          ))}
        </div>
      ) : null}
    </article>
  );
}

function RankTable({
  rows,
  maxAbsFlow,
}: {
  rows: SectorFlowRow[];
  maxAbsFlow: number;
}) {
  return (
    <div className="mf-table-wrap">
      <table className="mf-table">
        <thead>
          <tr>
            <th>#</th>
            <th>ETF</th>
            <th>Sector</th>
            <th>Dir</th>
            <th className="mf-num">1d</th>
            <th className="mf-num">5d</th>
            <th className="mf-num">RS5</th>
            <th className="mf-num">RS21</th>
            <th>Flow</th>
            <th>Def</th>
            <th className="mf-num">Rvol</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const score = r.flow_score;
            const w = flowBarWidth(score, maxAbsFlow);
            const side =
              score != null && score < 0
                ? "out"
                : score != null && score > 0
                  ? "in"
                  : "flat";
            return (
              <tr
                key={r.etf}
                className={`mf-row mf-row--${r.flow_direction || side}`}
              >
                <td className="tabular mf-muted">{r.rank ?? "—"}</td>
                <td>
                  <strong className="mf-etf">{r.etf}</strong>
                </td>
                <td>
                  <span className="mf-sector-name">{sectorLabel(r)}</span>
                  {r.bucket ? (
                    <span className="mf-bucket-tag">{r.bucket}</span>
                  ) : null}
                </td>
                <td>
                  <DirChip dir={r.flow_direction} />
                </td>
                <td className={`mf-num tabular mf-tone--${toneForPct(r.ret_1d)}`}>
                  {pctSigned(r.ret_1d)}
                </td>
                <td className={`mf-num tabular mf-tone--${toneForPct(r.ret_5d)}`}>
                  {pctSigned(r.ret_5d)}
                </td>
                <td className={`mf-num tabular mf-tone--${toneForPct(r.rs_5d)}`}>
                  {pctSigned(r.rs_5d)}
                </td>
                <td className={`mf-num tabular mf-tone--${toneForPct(r.rs_21d)}`}>
                  {pctSigned(r.rs_21d)}
                </td>
                <td className="mf-flow-cell">
                  <div className="mf-flow-bar" aria-hidden>
                    <div className="mf-flow-bar__mid" />
                    {side === "in" ? (
                      <div
                        className="mf-flow-bar__fill mf-flow-bar__fill--in"
                        style={{
                          left: "50%",
                          width: `${w / 2}%`,
                        }}
                      />
                    ) : null}
                    {side === "out" ? (
                      <div
                        className="mf-flow-bar__fill mf-flow-bar__fill--out"
                        style={{
                          right: "50%",
                          width: `${w / 2}%`,
                        }}
                      />
                    ) : null}
                  </div>
                  <span className="mf-flow-val tabular mf-muted">
                    {score != null && Number.isFinite(score)
                      ? score.toFixed(3)
                      : "—"}
                  </span>
                </td>
                <td>
                  <DefChip
                    definitive={r.definitive}
                    score={r.definitive_score}
                  />
                </td>
                <td className="mf-num tabular">
                  {r.rvol != null && Number.isFinite(r.rvol)
                    ? r.rvol.toFixed(2)
                    : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/* ─── Main desk ─── */

export function MoneyFlowDesk({ showHeader = false }: { showHeader?: boolean }) {
  const [source, setSource] = useState<SourceMode>("auto");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<MoneyFlowReport | null>(null);

  const run = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/sector-money-flow", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source }),
      });
      const json = (await res.json()) as {
        ok?: boolean;
        error?: string;
        data?: MoneyFlowReport;
      };
      if (!res.ok || !json.ok) {
        throw new Error(json.error || `Money flow failed (${res.status})`);
      }
      setReport(json.data ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [source]);

  // Auto-load once on mount
  useEffect(() => {
    void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional first load
  }, []);

  const ranked = report?.sectors_ranked || [];
  const moneyIn = report?.money_in?.length
    ? report.money_in
    : ranked.filter((r) => r.flow_direction === "in").slice(0, 5);
  const moneyOut = report?.money_out?.length
    ? report.money_out
    : ranked
        .filter((r) => r.flow_direction === "out")
        .slice()
        .sort(
          (a, b) =>
            (a.flow_score ?? 0) - (b.flow_score ?? 0),
        )
        .slice(0, 5);

  const maxAbsFlow = useMemo(() => {
    let m = 0.01;
    for (const r of ranked) {
      const s = r.flow_score;
      if (s != null && Number.isFinite(s)) m = Math.max(m, Math.abs(s));
    }
    return m;
  }, [ranked]);

  const rot = report?.rotation;
  const ctx = report?.market_context;
  const ratios = ctx?.ratios || {};
  const xlyXlp =
    rot?.xly_xlp_5d ??
    ratios.discretionary_vs_staples?.ret_5d ??
    null;
  const xlkXlp =
    rot?.xlk_xlp_5d ?? ratios.tech_vs_staples?.ret_5d ?? null;
  const semisTech =
    rot?.semis_vs_tech_1d ?? ratios.semis_vs_tech?.ret_1d ?? null;
  const themes =
    report?.theme_rotations ||
    rot?.theme_rotations ||
    [];
  const missingThemes = report?.missing_themes || [];

  return (
    <div className="mf-desk">
      {showHeader ? (
        <header className="mf-page-head">
          <h1 className="mf-page-title">Money Flow</h1>
          <p className="mf-page-desc">
            Where capital is rotating across sector books — and whether the move
            looks definitive.
          </p>
        </header>
      ) : null}

      <div className="mf-banner">
        <strong>OHLCV proxy</strong>
        <span>
          Relative strength vs SPY is a map of price leadership, not dark-pool
          tickets. Research only — not auto-execution.
        </span>
      </div>

      <div className="mf-controls">
        <label className="mf-label">
          Source
          <select
            className="mf-select"
            value={source}
            onChange={(e) => setSource(e.target.value as SourceMode)}
          >
            <option value="auto">Auto (local + SOXX/IGV Yahoo)</option>
            <option value="local">Local + themes</option>
            <option value="yfinance">Yahoo live</option>
          </select>
        </label>
        <button
          type="button"
          className="mf-btn"
          onClick={() => void run()}
          disabled={loading}
        >
          {loading ? "Scanning…" : "Refresh flow"}
        </button>
        {report?.asof_bar || report?.asof ? (
          <span className="mf-asof tabular">
            bar {report.asof_bar || "—"}
            {report.source ? ` · ${report.source}` : ""}
            {report.benchmark ? ` · vs ${report.benchmark}` : ""}
          </span>
        ) : null}
      </div>

      {error ? <p className="mf-error">{error}</p> : null}

      {!report && loading ? (
        <div className="mf-skeleton" aria-busy>
          <div className="mf-skeleton__hero" />
          <div className="mf-skeleton__cols">
            <div />
            <div />
          </div>
        </div>
      ) : null}

      {report?.ok === false ? (
        <p className="mf-error">{report.error || "Scan failed"}</p>
      ) : null}

      {report?.ok !== false && report && ranked.length > 0 ? (
        <>
          {/* Hero regime */}
          <section className={`mf-hero ${kindClass(rot?.kind)}`}>
            <div className="mf-hero__left">
              <span className="mf-hero__eyebrow">Rotation regime</span>
              <div className="mf-hero__title-row">
                <h2 className="mf-hero__kind">{kindLabel(rot?.kind)}</h2>
                <span
                  className={
                    rot?.is_definitive
                      ? "mf-hero-badge mf-hero-badge--yes"
                      : "mf-hero-badge mf-hero-badge--no"
                  }
                >
                  {rot?.is_definitive ? "DEFINITIVE" : "NOT DEFINITIVE"}
                </span>
              </div>
              <p className="mf-hero__summary">{rot?.summary || "—"}</p>
            </div>
            <div className="mf-hero__right">
              <span className="mf-hero__conf-label">Confidence</span>
              <ConfidenceMeter value={rot?.confidence} />
              <div className="mf-hero__ratios">
                <MetricPill
                  label="SOXX/XLK 1d"
                  value={pctSigned(semisTech)}
                  tone={toneForPct(semisTech)}
                />
                <MetricPill
                  label="XLK/XLP 5d"
                  value={pctSigned(xlkXlp)}
                  tone={toneForPct(xlkXlp)}
                />
                <MetricPill
                  label="XLY/XLP 5d"
                  value={pctSigned(xlyXlp)}
                  tone={toneForPct(xlyXlp)}
                />
              </div>
            </div>
          </section>

          {missingThemes.length > 0 ? (
            <p className="mf-error">
              Missing theme books (rotation map incomplete):{" "}
              {missingThemes.join(", ")}. Switch source to Auto/Yahoo and
              refresh.
            </p>
          ) : null}

          {themes.length > 0 ? (
            <section className="mf-themes" aria-label="Theme rotations">
              {themes.map((t) => (
                <div
                  key={t.id || t.label}
                  className={`mf-theme-card${t.id === "semis_to_tech" ? " mf-theme-card--hot" : ""}`}
                >
                  <div className="mf-theme-card__head">
                    <strong>{t.label || t.id}</strong>
                    <span className="mf-theme-card__path tabular">
                      {t.from_etf} → {t.to_etf}
                    </span>
                    {t.definitive ? (
                      <span className="mf-def mf-def--yes">DEFINITIVE</span>
                    ) : (
                      <span className="mf-def mf-def--no">SOFT</span>
                    )}
                  </div>
                  <p>{t.summary}</p>
                </div>
              ))}
            </section>
          ) : null}

          {/* Market strip */}
          <section className="mf-strip mf-strip--6" aria-label="Market context">
            <MetricPill
              label="SPY 1d"
              value={pctSigned(ctx?.spy_ret_1d)}
              tone={toneForPct(ctx?.spy_ret_1d)}
            />
            <MetricPill
              label="SPY 5d"
              value={pctSigned(ctx?.spy_ret_5d)}
              tone={toneForPct(ctx?.spy_ret_5d)}
            />
            <MetricPill
              label="SOXX RS 1d"
              value={pctSigned(
                (ctx as { soxx_rs_1d?: number | null })?.soxx_rs_1d ??
                  ranked.find((r) => r.etf === "SOXX")?.rs_1d,
              )}
              tone={toneForPct(
                (ctx as { soxx_rs_1d?: number | null })?.soxx_rs_1d ??
                  ranked.find((r) => r.etf === "SOXX")?.rs_1d,
              )}
            />
            <MetricPill
              label="XLK RS 1d"
              value={pctSigned(
                (ctx as { xlk_rs_1d?: number | null })?.xlk_rs_1d ??
                  ranked.find((r) => r.etf === "XLK")?.rs_1d,
              )}
              tone={toneForPct(
                (ctx as { xlk_rs_1d?: number | null })?.xlk_rs_1d ??
                  ranked.find((r) => r.etf === "XLK")?.rs_1d,
              )}
            />
            <MetricPill
              label="QQQ RS 5d"
              value={pctSigned(ctx?.qqq_spy_rs_5d)}
              tone={toneForPct(ctx?.qqq_spy_rs_5d)}
            />
            <MetricPill
              label="SPY MA20"
              value={
                ctx?.spy_above_ma20 == null
                  ? "—"
                  : ctx.spy_above_ma20
                    ? "above"
                    : "below"
              }
              tone={
                ctx?.spy_above_ma20 == null
                  ? "flat"
                  : ctx.spy_above_ma20
                    ? "up"
                    : "down"
              }
            />
          </section>

          {/* Money in / out */}
          <div className="mf-columns">
            <section className="mf-col mf-col--in">
              <header className="mf-col__head">
                <h3 className="mf-col__title">
                  <span className="mf-col__arrow" aria-hidden>
                    →
                  </span>{" "}
                  Money in
                </h3>
                <span className="mf-col__count">{moneyIn.length}</span>
              </header>
              {moneyIn.length === 0 ? (
                <p className="mf-empty">No clear inflows vs SPY</p>
              ) : (
                <div className="mf-card-stack">
                  {moneyIn.map((r) => (
                    <FlowCard key={r.etf} row={r} side="in" />
                  ))}
                </div>
              )}
            </section>

            <section className="mf-col mf-col--out">
              <header className="mf-col__head">
                <h3 className="mf-col__title">
                  <span className="mf-col__arrow" aria-hidden>
                    ←
                  </span>{" "}
                  Money out
                </h3>
                <span className="mf-col__count">{moneyOut.length}</span>
              </header>
              {moneyOut.length === 0 ? (
                <p className="mf-empty">No clear outflows vs SPY</p>
              ) : (
                <div className="mf-card-stack">
                  {moneyOut.map((r) => (
                    <FlowCard key={r.etf} row={r} side="out" />
                  ))}
                </div>
              )}
            </section>
          </div>

          {/* Full board */}
          <section className="mf-board">
            <header className="mf-board__head">
              <h3 className="mf-col__title">Sector board</h3>
              <span className="mf-muted">
                Ranked by composite flow (near-term RS hardest)
              </span>
            </header>
            <RankTable rows={ranked} maxAbsFlow={maxAbsFlow} />
          </section>

          {/* Watch names */}
          {(report.watch_names || []).length > 0 ? (
            <section className="mf-watch">
              <header className="mf-board__head">
                <h3 className="mf-col__title">Focus names</h3>
                <span className="mf-muted">
                  From leading books — open Analyze for a ticket
                </span>
              </header>
              <div className="mf-watch__grid">
                {(report.watch_names || []).slice(0, 16).map((n) => (
                  <Link
                    key={n.symbol}
                    href={analyzeHref({ symbol: n.symbol })}
                    className="mf-watch-card"
                  >
                    <span className="mf-watch-card__sym">{n.symbol}</span>
                    <span className="mf-watch-card__sec">
                      {n.sector_hint || n.etf || "—"}
                    </span>
                    <span
                      className={`mf-watch-card__rs tabular mf-tone--${toneForPct(n.rs_5d)}`}
                    >
                      {pctSigned(n.rs_5d)}
                    </span>
                    {n.parent_definitive ? (
                      <span className="mf-watch-card__def">DEF</span>
                    ) : null}
                  </Link>
                ))}
              </div>
            </section>
          ) : null}

          {/* Trading notes */}
          {(report.trading_notes || []).length > 0 ? (
            <section className="mf-notes">
              <header className="mf-board__head">
                <h3 className="mf-col__title">Keep in mind when trading</h3>
              </header>
              <ol className="mf-notes__list">
                {(report.trading_notes || []).map((note, i) => (
                  <li key={`${i}-${note.slice(0, 24)}`}>
                    <span className="mf-notes__num tabular">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span>{note}</span>
                  </li>
                ))}
              </ol>
            </section>
          ) : null}

          {report.disclaimer ? (
            <p className="mf-disclaimer">{report.disclaimer}</p>
          ) : null}
        </>
      ) : null}

      {report && !loading && ranked.length === 0 && report.ok !== false ? (
        <p className="mf-empty">No sector data returned. Try Yahoo live source.</p>
      ) : null}
    </div>
  );
}

export default MoneyFlowDesk;
