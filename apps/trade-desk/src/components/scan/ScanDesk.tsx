"use client";

import { useCallback, useMemo, useState } from "react";
import { analyzeHref, optionsHref } from "@/lib/routes";
import Link from "next/link";

export type ScanFlagMap = Record<string, boolean | undefined>;

export type ScanRow = {
  symbol: string;
  ok: boolean;
  error?: string;
  bias?: string;
  action?: string;
  side_hint?: string;
  close?: number;
  vwap?: number;
  above_vwap?: boolean;
  dist_vwap_atr?: number | null;
  vwap_policy?: string;
  vpa_tag?: string;
  vol_ratio?: number;
  flags?: ScanFlagMap;
  asof_bar?: string;
};

export type SectorLeader = {
  etf: string;
  sector: string;
  score?: number;
  rs_5d?: number;
  rs_21d?: number;
  names?: string[];
};

export type WatchName = {
  symbol: string;
  sector_hint?: string;
  score?: number;
  rs_5d?: number;
  rs_21d?: number;
};

export type SectorBlock = {
  ok?: boolean;
  leaders?: SectorLeader[];
  laggards?: SectorLeader[];
  watch_names?: WatchName[];
  narrative?: string[];
  disclaimer?: string;
};

export type ScanPayload = {
  ok?: boolean;
  asof?: string;
  disclaimer?: string;
  gate_80_wr?: boolean;
  count?: number;
  calls?: ScanRow[];
  puts?: ScanRow[];
  rows?: ScanRow[];
  sectors?: SectorBlock;
};

const DEFAULT_SYMBOLS =
  "TSLA,MSTR,NVDA,AMD,META,HOOD,IONQ,MU,AVGO,AAPL,AMZN,GOOGL,ARM";

function pct(n: number | undefined | null, digits = 1): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}

function biasClass(bias: string | undefined): string {
  if (!bias) return "scan-bias scan-bias--flat";
  if (bias.startsWith("CALL")) return "scan-bias scan-bias--call";
  if (bias.startsWith("PUT")) return "scan-bias scan-bias--put";
  if (bias === "CONFLICT") return "scan-bias scan-bias--conflict";
  return "scan-bias scan-bias--flat";
}

function policyChip(pol: string | undefined): string {
  const p = (pol || "soft").toLowerCase();
  return `scan-policy scan-policy--${p}`;
}

function FlagPills({ flags }: { flags?: ScanFlagMap }) {
  if (!flags) return null;
  const active = Object.entries(flags)
    .filter(([, v]) => v)
    .map(([k]) => k.replace(/_/g, " "));
  if (!active.length) return <span className="scan-muted">—</span>;
  return (
    <div className="scan-flags">
      {active.slice(0, 5).map((f) => (
        <span key={f} className="scan-flag">
          {f}
        </span>
      ))}
    </div>
  );
}

function BiasCard({
  title,
  tone,
  rows,
}: {
  title: string;
  tone: "call" | "put";
  rows: ScanRow[];
}) {
  return (
    <section className={`scan-panel scan-panel--${tone}`}>
      <header className="scan-panel__head">
        <h2 className="scan-panel__title">{title}</h2>
        <span className="scan-panel__count">{rows.length}</span>
      </header>
      {rows.length === 0 ? (
        <p className="scan-empty">No {tone.toUpperCase()} bias names</p>
      ) : (
        <ul className="scan-list">
          {rows.map((r) => (
            <li key={r.symbol} className="scan-card">
              <div className="scan-card__top">
                <Link
                  href={analyzeHref({ symbol: r.symbol })}
                  className="scan-sym"
                >
                  {r.symbol}
                </Link>
                <span className={biasClass(r.bias)}>{r.bias}</span>
                <span className={policyChip(r.vwap_policy)}>
                  peg:{r.vwap_policy || "soft"}
                </span>
              </div>
              <div className="scan-card__meta">
                <span className="tabular">
                  ${r.close?.toFixed(2) ?? "—"}
                </span>
                <span className="scan-muted">
                  VWAP {r.vwap != null && Number.isFinite(r.vwap)
                    ? `$${r.vwap.toFixed(2)}`
                    : "—"}
                </span>
                <span
                  className={
                    r.above_vwap ? "scan-peg-up" : "scan-peg-down"
                  }
                >
                  {r.above_vwap ? "above" : "below"}
                </span>
              </div>
              <p className="scan-tag">{r.vpa_tag || "—"}</p>
              <p className="scan-action">{r.action}</p>
              <FlagPills flags={r.flags} />
              <div className="scan-card__links">
                <Link href={optionsHref(r.symbol)}>Options →</Link>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function AllTable({ rows }: { rows: ScanRow[] }) {
  return (
    <div className="scan-table-wrap">
      <table className="scan-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Bias</th>
            <th>Close</th>
            <th>VWAP</th>
            <th>Policy</th>
            <th>VPA tag</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.symbol} className={!r.ok ? "scan-row--err" : undefined}>
              <td>
                <Link href={analyzeHref({ symbol: r.symbol })} className="scan-sym">
                  {r.symbol}
                </Link>
              </td>
              <td>
                {r.ok ? (
                  <span className={biasClass(r.bias)}>{r.bias}</span>
                ) : (
                  <span className="scan-bias scan-bias--flat">ERR</span>
                )}
              </td>
              <td className="tabular">
                {r.ok && r.close != null ? r.close.toFixed(2) : "—"}
              </td>
              <td className="tabular">
                {r.ok && r.vwap != null && Number.isFinite(r.vwap)
                  ? r.vwap.toFixed(2)
                  : "—"}
              </td>
              <td>
                <span className={policyChip(r.vwap_policy)}>
                  {r.vwap_policy || "—"}
                </span>
              </td>
              <td className="scan-tag-cell">{r.vpa_tag || r.error || "—"}</td>
              <td className="scan-action-cell">{r.action || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SectorPanel({ sectors }: { sectors: SectorBlock }) {
  if (!sectors?.ok) return null;
  return (
    <section className="scan-sectors">
      <header className="scan-panel__head">
        <h2 className="scan-panel__title">Weekly sector RS vs SPY</h2>
      </header>
      {sectors.narrative?.length ? (
        <ul className="scan-narrative">
          {sectors.narrative.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      ) : null}
      <div className="scan-sector-grid">
        <div>
          <h3 className="scan-subhead">Leaders</h3>
          <ul className="scan-sector-list">
            {(sectors.leaders || []).map((s) => (
              <li key={s.etf}>
                <strong>{s.etf}</strong> {s.sector}{" "}
                <span className="tabular scan-peg-up">{pct(s.score)}</span>
                <span className="scan-muted">
                  {" "}
                  rs21 {pct(s.rs_21d)}
                </span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="scan-subhead">Laggards</h3>
          <ul className="scan-sector-list">
            {(sectors.laggards || []).map((s) => (
              <li key={s.etf}>
                <strong>{s.etf}</strong> {s.sector}{" "}
                <span className="tabular scan-peg-down">{pct(s.score)}</span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="scan-subhead">Watch names</h3>
          <ul className="scan-sector-list">
            {(sectors.watch_names || []).slice(0, 10).map((n) => (
              <li key={n.symbol}>
                <Link href={analyzeHref({ symbol: n.symbol })} className="scan-sym">
                  {n.symbol}
                </Link>{" "}
                <span className="scan-muted">{n.sector_hint}</span>{" "}
                <span className="tabular">{pct(n.score)}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
      {sectors.disclaimer ? (
        <p className="scan-disclaimer-sm">{sectors.disclaimer}</p>
      ) : null}
    </section>
  );
}

export function ScanDesk() {
  const [symbols, setSymbols] = useState(DEFAULT_SYMBOLS);
  const [withSectors, setWithSectors] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [payload, setPayload] = useState<ScanPayload | null>(null);

  const run = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/vpa-scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbols: symbols
            .split(/[,\s]+/)
            .map((s) => s.trim().toUpperCase())
            .filter(Boolean),
          withSectors,
        }),
      });
      const json = (await res.json()) as {
        ok?: boolean;
        error?: string;
        data?: ScanPayload;
      };
      if (!res.ok || !json.ok) {
        throw new Error(json.error || `Scan failed (${res.status})`);
      }
      setPayload(json.data ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [symbols, withSectors]);

  const calls = useMemo(() => {
    if (payload?.calls?.length) return payload.calls;
    return (payload?.rows || []).filter(
      (r) =>
        r.ok &&
        String(r.bias || "").startsWith("CALL") &&
        !String(r.bias || "").includes("WEAK"),
    );
  }, [payload]);

  const puts = useMemo(() => {
    if (payload?.puts?.length) return payload.puts;
    return (payload?.rows || []).filter(
      (r) =>
        r.ok &&
        String(r.bias || "").startsWith("PUT") &&
        !String(r.bias || "").includes("WEAK"),
    );
  }, [payload]);

  const allRows = payload?.rows || [];
  const gate80 = Boolean(payload?.gate_80_wr);

  return (
    <div className="scan-desk">
      <div className={gate80 ? "scan-banner scan-banner--ok" : "scan-banner"}>
        {gate80 ? (
          <strong>80% WR gate: PASS</strong>
        ) : (
          <>
            <strong>RESEARCH ONLY — not Live auto</strong>
            <span>
              {" "}
              VPA + swing VWAP DNA tags. Pure OOS win rate is below the ~80%
              promotion bar. Use as a discretionary checklist, not auto
              execution.
            </span>
          </>
        )}
      </div>

      <div className="scan-controls">
        <label className="scan-label">
          Symbols
          <input
            className="scan-input"
            value={symbols}
            onChange={(e) => setSymbols(e.target.value)}
            placeholder="TSLA, NVDA, …"
            spellCheck={false}
          />
        </label>
        <label className="scan-check">
          <input
            type="checkbox"
            checked={withSectors}
            onChange={(e) => setWithSectors(e.target.checked)}
          />
          Include sector RS / weekly watch
        </label>
        <button
          type="button"
          className="scan-btn"
          onClick={run}
          disabled={loading}
        >
          {loading ? "Scanning…" : "Run VPA scan"}
        </button>
      </div>

      {error ? <p className="scan-error">{error}</p> : null}
      {payload?.disclaimer ? (
        <p className="scan-disclaimer">{payload.disclaimer}</p>
      ) : null}
      {payload?.asof ? (
        <p className="scan-meta">
          asof {payload.asof} · {payload.count ?? allRows.length} names
        </p>
      ) : null}

      {payload?.sectors ? <SectorPanel sectors={payload.sectors} /> : null}

      <div className="scan-columns">
        <BiasCard title="CALL bias" tone="call" rows={calls} />
        <BiasCard title="PUT bias" tone="put" rows={puts} />
      </div>

      {allRows.length > 0 ? (
        <section className="scan-all">
          <h2 className="scan-panel__title">Full scan</h2>
          <AllTable rows={allRows} />
        </section>
      ) : null}
    </div>
  );
}
