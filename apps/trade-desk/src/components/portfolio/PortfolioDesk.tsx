"use client";

import { useState } from "react";
import { PageHeader } from "@/components/shell/PageHeader";
import { formatPct, formatNum } from "@/lib/format";
import type { ApiEnvelope, PortfolioMethod, PortfolioOptimizerResponse } from "@/lib/types";
import { PortfolioBuilder } from "./PortfolioBuilder";

type MptAsset = { name: string; ret: number; vol: number };
type RpAsset = { name: string; vol: number };
type Factor = { premium: number; vol: number };

const DEFAULT_MPT: MptAsset[] = [
  { name: "Equities", ret: 12, vol: 20 },
  { name: "Bonds", ret: 6, vol: 10 },
];

const DEFAULT_RP: RpAsset[] = [
  { name: "Equities", vol: 16 },
  { name: "Bonds", vol: 5 },
  { name: "Commodities", vol: 18 },
  { name: "Real Estate", vol: 13 },
];

const DEFAULT_FACTORS: Record<string, Factor> = {
  Value: { premium: 3.2, vol: 5 },
  Momentum: { premium: 7.5, vol: 8 },
  Quality: { premium: 4.1, vol: 5 },
  Size: { premium: 2.8, vol: 7 },
  "Low Volatility": { premium: 3.5, vol: 4 },
};

const DEFAULT_TILTS: Record<string, number> = {
  Value: 0,
  Momentum: 0,
  Quality: 0,
  Size: 0,
  "Low Volatility": 0,
};

const TABS: { key: PortfolioMethod; label: string }[] = [
  { key: "portfolio", label: "My Portfolio" },
  { key: "mpt", label: "MPT / Efficient Frontier" },
  { key: "risk_parity", label: "Risk Parity" },
  { key: "factor_tilt", label: "Factor Tilt" },
];

function buildCorrelation(n: number, off: number): number[][] {
  return Array.from({ length: n }, (_, i) =>
    Array.from({ length: n }, (_, j) => (i === j ? 1 : off)),
  );
}

function usePortfolio() {
  const [result, setResult] = useState<PortfolioOptimizerResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (method: PortfolioMethod, payload: Record<string, unknown>) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/portfolio", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const json = (await res.json()) as ApiEnvelope<PortfolioOptimizerResponse>;
      if (!res.ok || json.ok === false || !json.data) {
        throw new Error(json.error || "Portfolio optimization failed");
      }
      setResult(json.data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  return { result, loading, error, run };
}

function MptPanel({
  result,
  loading,
  error,
  onRun,
}: {
  result: PortfolioOptimizerResponse | null;
  loading: boolean;
  error: string | null;
  onRun: (payload: Record<string, unknown>) => void;
}) {
  const [assets, setAssets] = useState(DEFAULT_MPT);
  const [correlation, setCorrelation] = useState(0.3);
  const [riskFree, setRiskFree] = useState(3);

  const submit = () => {
    onRun({
      method: "mpt",
      risk_free: riskFree / 100,
      assets: assets.map((a) => ({ name: a.name, ret: a.ret / 100, vol: a.vol / 100 })),
      correlation: buildCorrelation(assets.length, correlation),
      frontier_points: 50,
    });
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="td-panel p-3">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {assets.map((a, i) => (
            <div key={a.name} className="flex flex-col gap-2">
              <div className="text-[var(--td-ink-200)] font-medium">{a.name}</div>
              <div className="grid grid-cols-2 gap-2">
                <label className="td-field">
                  <span className="td-label">Return %</span>
                  <input
                    type="number"
                    className="td-input tabular"
                    value={a.ret}
                    onChange={(e) => {
                      const next = [...assets];
                      next[i] = { ...next[i], ret: Number(e.target.value) };
                      setAssets(next);
                    }}
                    step={0.1}
                  />
                </label>
                <label className="td-field">
                  <span className="td-label">Vol %</span>
                  <input
                    type="number"
                    className="td-input tabular"
                    value={a.vol}
                    onChange={(e) => {
                      const next = [...assets];
                      next[i] = { ...next[i], vol: Number(e.target.value) };
                      setAssets(next);
                    }}
                    step={0.1}
                  />
                </label>
              </div>
            </div>
          ))}
        </div>
        <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2">
          <label className="td-field">
            <span className="td-label">Correlation</span>
            <input
              type="number"
              className="td-input tabular"
              value={correlation}
              onChange={(e) => setCorrelation(Number(e.target.value))}
              step={0.05}
              min={-1}
              max={1}
            />
          </label>
          <label className="td-field">
            <span className="td-label">Risk-free %</span>
            <input
              type="number"
              className="td-input tabular"
              value={riskFree}
              onChange={(e) => setRiskFree(Number(e.target.value))}
              step={0.1}
            />
          </label>
        </div>
        <div className="mt-3">
          <button
            className="td-btn td-btn-primary"
            onClick={submit}
            disabled={loading}
          >
            {loading ? "Optimising…" : "Run"}
          </button>
        </div>
      </div>

      {error ? (
        <div className="td-alert td-alert--error" role="alert">
          {error}
        </div>
      ) : null}

      {result?.method === "mpt" ? (
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <div className="td-panel p-3">
              <div className="text-[var(--td-ink-400)] text-[11px] uppercase tracking-wide mb-2">
                Max Sharpe (Tangency)
              </div>
              <div className="text-[var(--td-ink-100)] font-medium tabular">
                {formatPct(result.max_sharpe?.return, 1)} ret · {formatPct(result.max_sharpe?.risk, 1)} vol · SR {formatNum(result.max_sharpe?.sharpe, 2)}
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2 text-[12px]">
                {result.assets?.map((a, i) => {
                  const name = typeof a === "string" ? a : a.name;
                  return (
                    <div key={name} className="flex justify-between">
                      <span className="text-[var(--td-ink-300)]">{name}</span>
                      <span className="tabular text-[var(--td-ink-100)]">
                        {formatPct((result.max_sharpe?.weights?.[i] ?? 0), 0)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
            <div className="td-panel p-3">
              <div className="text-[var(--td-ink-400)] text-[11px] uppercase tracking-wide mb-2">
                Min Variance
              </div>
              <div className="text-[var(--td-ink-100)] font-medium tabular">
                {formatPct(result.min_variance?.return, 1)} ret · {formatPct(result.min_variance?.risk, 1)} vol · SR {formatNum(result.min_variance?.sharpe, 2)}
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2 text-[12px]">
                {result.assets?.map((a, i) => {
                  const name = typeof a === "string" ? a : a.name;
                  return (
                    <div key={name} className="flex justify-between">
                      <span className="text-[var(--td-ink-300)]">{name}</span>
                      <span className="tabular text-[var(--td-ink-100)]">
                        {formatPct((result.min_variance?.weights?.[i] ?? 0), 0)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          <details className="td-details td-details--block" open>
            <summary className="td-details__summary">Efficient frontier</summary>
            <div className="overflow-x-auto mt-2">
              <table className="scan-table">
                <thead>
                  <tr>
                    <th>Return</th>
                    <th>Risk</th>
                    <th>Sharpe</th>
                    {result.assets?.map((a) => {
                      const name = typeof a === "string" ? a : a.name;
                      return <th key={name}>{name}</th>;
                    })}
                  </tr>
                </thead>
                <tbody>
                  {result.efficient_frontier?.map((p, idx) => (
                    <tr key={idx}>
                      <td className="tabular">{formatPct(p.return, 1)}</td>
                      <td className="tabular">{formatPct(p.risk, 1)}</td>
                      <td className="tabular">{formatNum(p.sharpe, 2)}</td>
                      {p.weights?.map((w, j) => (
                        <td key={j} className="tabular">{formatPct(w, 0)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>

          <details className="td-details td-details--block">
            <summary className="td-details__summary">Capital Market Line</summary>
            <div className="overflow-x-auto mt-2">
              <table className="scan-table">
                <thead>
                  <tr>
                    <th>Allocation</th>
                    <th>Return</th>
                    <th>Risk</th>
                    <th>Sharpe</th>
                  </tr>
                </thead>
                <tbody>
                  {result.capital_market_line?.map((p, idx) => (
                    <tr key={idx}>
                      <td className="tabular">{formatPct(p.allocation ?? 0, 0)}</td>
                      <td className="tabular">{formatPct(p.return, 1)}</td>
                      <td className="tabular">{formatPct(p.risk, 1)}</td>
                      <td className="tabular">{formatNum(p.sharpe, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </div>
      ) : null}
    </div>
  );
}

function RiskParityPanel({
  result,
  loading,
  error,
  onRun,
}: {
  result: PortfolioOptimizerResponse | null;
  loading: boolean;
  error: string | null;
  onRun: (payload: Record<string, unknown>) => void;
}) {
  const [assets, setAssets] = useState(DEFAULT_RP);
  const [correlation, setCorrelation] = useState(0.0);

  const submit = () => {
    onRun({
      method: "risk_parity",
      assets: assets.map((a) => ({ name: a.name, vol: a.vol / 100 })),
      correlation: buildCorrelation(assets.length, correlation),
    });
  };

  const rows = ["equal_weight", "inverse_volatility", "equal_risk_contribution"];

  return (
    <div className="flex flex-col gap-3">
      <div className="td-panel p-3">
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
          {assets.map((a, i) => (
            <label key={a.name} className="td-field">
              <span className="td-label">{a.name} vol %</span>
              <input
                type="number"
                className="td-input tabular"
                value={a.vol}
                onChange={(e) => {
                  const next = [...assets];
                  next[i] = { ...next[i], vol: Number(e.target.value) };
                  setAssets(next);
                }}
                step={0.1}
              />
            </label>
          ))}
        </div>
        <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2">
          <label className="td-field">
            <span className="td-label">Pairwise correlation</span>
            <input
              type="number"
              className="td-input tabular"
              value={correlation}
              onChange={(e) => setCorrelation(Number(e.target.value))}
              step={0.05}
              min={-1}
              max={1}
            />
          </label>
        </div>
        <div className="mt-3">
          <button className="td-btn td-btn-primary" onClick={submit} disabled={loading}>
            {loading ? "Optimising…" : "Run"}
          </button>
        </div>
      </div>

      {error ? (
        <div className="td-alert td-alert--error" role="alert">
          {error}
        </div>
      ) : null}

      {result?.method === "risk_parity" ? (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {rows.map((key) => {
            const data =
              key === "equal_weight"
                ? result.equal_weight
                : key === "inverse_volatility"
                ? result.inverse_volatility
                : result.equal_risk_contribution;
            return (
              <div key={key} className="td-panel p-3">
                <div className="text-[var(--td-ink-400)] text-[11px] uppercase tracking-wide mb-2">
                  {key.replace(/_/g, " ")}
                </div>
                <div className="text-[var(--td-ink-100)] font-medium tabular mb-2">
                  risk {formatPct(data?.risk, 1)}
                </div>
                <div className="overflow-x-auto">
                  <table className="scan-table">
                    <thead>
                      <tr>
                        <th>Asset</th>
                        <th className="text-right">Weight</th>
                        <th className="text-right">Risk %</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.assets?.map((a) => {
                        const name = typeof a === "string" ? a : a.name;
                        return (
                          <tr key={name}>
                            <td>{name}</td>
                            <td className="tabular text-right">{formatPct(data?.weights?.[name] ?? 0, 0)}</td>
                            <td className="tabular text-right">{formatPct(data?.risk_contribution?.[name] ?? 0, 0)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

function FactorTiltPanel({
  result,
  loading,
  error,
  onRun,
}: {
  result: PortfolioOptimizerResponse | null;
  loading: boolean;
  error: string | null;
  onRun: (payload: Record<string, unknown>) => void;
}) {
  const [marketReturn, setMarketReturn] = useState(8);
  const [marketVol, setMarketVol] = useState(15);
  const [riskFree, setRiskFree] = useState(3);
  const [factors] = useState(DEFAULT_FACTORS);
  const [tilts, setTilts] = useState(DEFAULT_TILTS);

  const submit = () => {
    onRun({
      method: "factor_tilt",
      market_return: marketReturn / 100,
      market_vol: marketVol / 100,
      risk_free: riskFree / 100,
      factors: Object.fromEntries(
        Object.entries(factors).map(([k, v]) => [k, { premium: v.premium / 100, vol: v.vol / 100 }]),
      ),
      tilts: Object.fromEntries(
        Object.entries(tilts).map(([k, v]) => [k, v / 100]),
      ),
    });
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="td-panel p-3">
        <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
          <label className="td-field">
            <span className="td-label">Market return %</span>
            <input
              type="number"
              className="td-input tabular"
              value={marketReturn}
              onChange={(e) => setMarketReturn(Number(e.target.value))}
              step={0.1}
            />
          </label>
          <label className="td-field">
            <span className="td-label">Market vol %</span>
            <input
              type="number"
              className="td-input tabular"
              value={marketVol}
              onChange={(e) => setMarketVol(Number(e.target.value))}
              step={0.1}
            />
          </label>
          <label className="td-field">
            <span className="td-label">Risk-free %</span>
            <input
              type="number"
              className="td-input tabular"
              value={riskFree}
              onChange={(e) => setRiskFree(Number(e.target.value))}
              step={0.1}
            />
          </label>
        </div>
        <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2">
          {Object.entries(factors).map(([name, data]) => (
            <label key={name} className="td-field">
              <span className="td-label">
                {name} tilt ({data.premium}%)
              </span>
              <input
                type="number"
                className="td-input tabular"
                value={tilts[name]}
                onChange={(e) =>
                  setTilts((prev) => ({ ...prev, [name]: Number(e.target.value) }))
                }
                step={1}
                min={0}
                max={100}
              />
            </label>
          ))}
        </div>
        <div className="mt-3">
          <button className="td-btn td-btn-primary" onClick={submit} disabled={loading}>
            {loading ? "Optimising…" : "Run"}
          </button>
        </div>
      </div>

      {error ? (
        <div className="td-alert td-alert--error" role="alert">
          {error}
        </div>
      ) : null}

      {result?.method === "factor_tilt" ? (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <div className="td-panel p-3">
            <div className="text-[var(--td-ink-400)] text-[11px] uppercase tracking-wide mb-2">
              Tilted portfolio
            </div>
            <div className="grid grid-cols-2 gap-2 text-[12px]">
              <div>
                <div className="text-[var(--td-ink-400)]">Expected return</div>
                <div className="tabular text-[var(--td-ink-100)]">{formatPct(result.expected_return, 1)}</div>
              </div>
              <div>
                <div className="text-[var(--td-ink-400)]">Portfolio risk</div>
                <div className="tabular text-[var(--td-ink-100)]">{formatPct(result.portfolio_risk, 1)}</div>
              </div>
              <div>
                <div className="text-[var(--td-ink-400)]">Tracking error</div>
                <div className="tabular text-[var(--td-ink-100)]">{formatPct(result.tracking_error, 1)}</div>
              </div>
              <div>
                <div className="text-[var(--td-ink-400)]">Sharpe</div>
                <div className="tabular text-[var(--td-ink-100)]">{formatNum(result.sharpe, 2)}</div>
              </div>
            </div>
          </div>
          <div className="td-panel p-3">
            <div className="text-[var(--td-ink-400)] text-[11px] uppercase tracking-wide mb-2">
              Return contribution by factor
            </div>
            <div className="overflow-x-auto">
              <table className="scan-table">
                <thead>
                  <tr>
                    <th>Source</th>
                    <th className="text-right">Contribution</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(result.contributions ?? {}).map(([source, val]) => (
                    <tr key={source}>
                      <td>{source}</td>
                      <td className="tabular text-right">{formatPct(val, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function PortfolioDesk({ showHeader = true }: { showHeader?: boolean }) {
  const [tab, setTab] = useState<PortfolioMethod>("portfolio");
  const { result, loading, error, run } = usePortfolio();

  const runTab = (payload: Record<string, unknown>) => {
    run(payload.method as PortfolioMethod, payload);
  };

  const body = (
    <>
      {showHeader ? (
        <PageHeader
          title="Portfolio"
          description="Construction metrics on inputs you set — mean-variance, efficient frontier, risk parity, and factor tilt."
        />
      ) : null}

      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Portfolio methods">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            className={`td-btn ${tab === t.key ? "td-btn-primary" : "td-btn-ghost"}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div role="tabpanel" aria-label={TABS.find((t) => t.key === tab)?.label}>
        {tab === "portfolio" ? (
          <PortfolioBuilder />
        ) : tab === "mpt" ? (
          <MptPanel result={result} loading={loading} error={error} onRun={runTab} />
        ) : tab === "risk_parity" ? (
          <RiskParityPanel result={result} loading={loading} error={error} onRun={runTab} />
        ) : (
          <FactorTiltPanel result={result} loading={loading} error={error} onRun={runTab} />
        )}
      </div>
    </>
  );

  return showHeader ? <div className="td-page">{body}</div> : <div className="flex flex-col gap-3">{body}</div>;
}
