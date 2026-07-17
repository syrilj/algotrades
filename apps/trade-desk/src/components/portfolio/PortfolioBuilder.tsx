"use client";

import { useEffect, useState } from "react";
import { formatPct, formatNum, formatUsd } from "@/lib/format";
import { colorVarFor } from "@/lib/actionColors";
import type { ApiEnvelope, PaperPosition, PortfolioOptimizationResponse } from "@/lib/types";

type BasketItem = { symbol: string; shares: number; mark?: number | null };

type PickRow = {
  symbol: string;
  action?: string;
  setup_kind?: string;
  score?: number;
  price?: number;
  confidence?: number;
  hit_probability?: number;
  model?: string;
  do_next?: string;
  error?: string;
};

const DEFAULT_RISK_FREE = 3;
const DEFAULT_LOOKBACK = 252;
const DEFAULT_ACCOUNT = 0;

function sanitizeSymbol(s: string) {
  return s.trim().toUpperCase().replace(/\.US$/i, "");
}

export function PortfolioBuilder() {
  const [basket, setBasket] = useState<BasketItem[]>([]);
  const [newSymbol, setNewSymbol] = useState("");
  const [newShares, setNewShares] = useState<number | "">("");
  const [riskFree, setRiskFree] = useState(DEFAULT_RISK_FREE);
  const [lookback, setLookback] = useState(DEFAULT_LOOKBACK);
  const [account, setAccount] = useState<number | "">(DEFAULT_ACCOUNT);
  const [loading, setLoading] = useState(false);
  const [loadingPositions, setLoadingPositions] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PortfolioOptimizationResponse | null>(null);
  const [analysis, setAnalysis] = useState<PickRow[] | null>(null);

  useEffect(() => {
    void loadPositions();
  }, []);

  const loadPositions = async () => {
    setLoadingPositions(true);
    setError(null);
    try {
      const res = await fetch("/api/positions?status=open&mark=1", { method: "GET" });
      const json = (await res.json()) as ApiEnvelope<{
        positions: PaperPosition[];
        asof?: string;
      }>;
      if (!res.ok || json.ok === false || !json.data) {
        throw new Error(json.error || "Failed to load positions");
      }
      const next: BasketItem[] = [];
      const map = new Map<string, BasketItem>();
      for (const p of json.data.positions || []) {
        if (p.status !== "open") continue;
        if (p.side !== "long") continue;
        const symbol = sanitizeSymbol(p.symbol);
        const existing = map.get(symbol);
        if (existing) {
          existing.shares += p.shares;
          if (p.mark != null) existing.mark = p.mark;
          continue;
        }
        const item: BasketItem = { symbol, shares: p.shares, mark: p.mark ?? null };
        map.set(symbol, item);
        next.push(item);
      }
      setBasket(next);
      setResult(null);
      setAnalysis(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingPositions(false);
    }
  };

  const addSymbol = () => {
    const symbol = sanitizeSymbol(newSymbol);
    if (!symbol) return;
    const shares = typeof newShares === "number" ? newShares : 1;
    setBasket((prev) => {
      const existing = prev.find((i) => i.symbol === symbol);
      if (existing) {
        return prev.map((i) => (i.symbol === symbol ? { ...i, shares: i.shares + shares } : i));
      }
      return [...prev, { symbol, shares }];
    });
    setNewSymbol("");
    setNewShares("");
    setResult(null);
    setAnalysis(null);
  };

  const removeSymbol = (symbol: string) => {
    setBasket((prev) => prev.filter((i) => i.symbol !== symbol));
    setResult(null);
    setAnalysis(null);
  };

  const updateShares = (symbol: string, value: number) => {
    setBasket((prev) => prev.map((i) => (i.symbol === symbol ? { ...i, shares: value } : i)));
    setResult(null);
    setAnalysis(null);
  };

  const analyzeBasket = async () => {
    if (basket.length === 0) {
      setError("Add symbols to analyze");
      return;
    }
    setAnalyzing(true);
    setError(null);
    try {
      const payload: Record<string, unknown> = {
        symbols: basket.map((i) => i.symbol),
        horizon: "day",
        model: "auto",
        riskPct: 1,
      };
      if (account !== "" && account > 0) payload.account = account;
      const res = await fetch("/api/picks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const json = (await res.json()) as ApiEnvelope<{ picks?: PickRow[] }>;
      if (!res.ok || json.ok === false || !json.data) {
        throw new Error(json.error || "Analysis failed");
      }
      setAnalysis(json.data.picks || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setAnalyzing(false);
    }
  };

  const optimize = async () => {
    if (basket.length < 2) {
      setError("Add at least 2 symbols to optimize");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const payload: Record<string, unknown> = {
        method: "portfolio",
        symbols: basket.map((i) => i.symbol),
        holdings: Object.fromEntries(basket.map((i) => [i.symbol, i.shares])),
        risk_free: riskFree / 100,
        lookback: lookback,
        mode: "both",
      };
      if (account !== "" && account > 0) payload.account = account;
      const res = await fetch("/api/portfolio", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const json = (await res.json()) as ApiEnvelope<PortfolioOptimizationResponse>;
      if (!res.ok || json.ok === false || !json.data) {
        throw new Error(json.error || "Portfolio optimization failed");
      }
      setResult(json.data);
      setBasket((prev) =>
        prev.map((i) => ({
          ...i,
          mark: json.data?.last_prices[i.symbol] ?? i.mark,
        })),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const basketValue = result
    ? result.total_market_value
    : basket.reduce((sum, i) => sum + (i.mark ?? 0) * i.shares, 0);

  return (
    <div className="flex flex-col gap-3">
      <div className="td-panel p-3">
        <div className="flex flex-wrap items-end gap-3">
          <button
            className="td-btn td-btn-primary"
            onClick={loadPositions}
            disabled={loadingPositions}
          >
            {loadingPositions ? "Loading…" : "Load from positions"}
          </button>
          <div className="flex flex-1 gap-2">
            <input
              type="text"
              className="td-input tabular"
              placeholder="Symbol"
              value={newSymbol}
              onChange={(e) => setNewSymbol(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addSymbol()}
              style={{ width: "120px" }}
            />
            <input
              type="number"
              className="td-input tabular"
              placeholder="Shares"
              value={newShares}
              onChange={(e) => setNewShares(e.target.value === "" ? "" : Number(e.target.value))}
              onKeyDown={(e) => e.key === "Enter" && addSymbol()}
              style={{ width: "120px" }}
            />
            <button className="td-btn td-btn-ghost" onClick={addSymbol}>
              Add
            </button>
          </div>
        </div>

        {basket.length > 0 ? (
          <div className="mt-3 overflow-x-auto">
            <table className="scan-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th className="text-right">Shares</th>
                  <th className="text-right">Mark</th>
                  <th className="text-right">Value</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {basket.map((item) => {
                  const value = (item.mark ?? 0) * item.shares;
                  return (
                    <tr key={item.symbol}>
                      <td className="font-medium">{item.symbol}</td>
                      <td className="text-right">
                        <input
                          type="number"
                          className="td-input tabular"
                          value={item.shares}
                          onChange={(e) => updateShares(item.symbol, Number(e.target.value))}
                          style={{ width: "100px" }}
                        />
                      </td>
                      <td className="tabular text-right">
                        {item.mark ? formatUsd(item.mark) : "—"}
                      </td>
                      <td className="tabular text-right">
                        {value ? formatUsd(value) : "—"}
                      </td>
                      <td className="text-right">
                        <button
                          className="td-btn td-btn-ghost text-[var(--td-avoid)]"
                          onClick={() => removeSymbol(item.symbol)}
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div className="mt-2 text-right text-[var(--td-ink-200)] text-[12px]">
              Basket value: {formatUsd(basketValue)} (from {basket.length} symbols)
            </div>
          </div>
        ) : (
          <div className="mt-3 text-[var(--td-ink-400)] text-[12px]">
            No symbols. Load from your paper ledger or add a symbol above.
          </div>
        )}

        <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-3">
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
          <label className="td-field">
            <span className="td-label">Lookback (days)</span>
            <input
              type="number"
              className="td-input tabular"
              value={lookback}
              onChange={(e) => setLookback(Number(e.target.value))}
              step={30}
            />
          </label>
          <label className="td-field">
            <span className="td-label">Account $ (optional)</span>
            <input
              type="number"
              className="td-input tabular"
              value={account}
              onChange={(e) => setAccount(e.target.value === "" ? "" : Number(e.target.value))}
              placeholder="Current portfolio value"
            />
          </label>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <button className="td-btn td-btn-primary" onClick={optimize} disabled={loading || basket.length < 2}>
            {loading ? "Computing…" : "Compute weight scenarios"}
          </button>
          <button className="td-btn td-btn-ghost" onClick={analyzeBasket} disabled={analyzing || basket.length === 0}>
            {analyzing ? "Loading path…" : "Load model path per symbol"}
          </button>
        </div>
        <p className="mt-2 text-[11px]" style={{ color: "var(--td-ink-400)" }}>
          Scenarios and path labels are metrics under the chosen model contract —
          not target trades or sizing instructions.
        </p>
      </div>

      {error ? (
        <div className="td-alert td-alert--error" role="alert">
          {error}
        </div>
      ) : null}

      {analysis ? <PortfolioAnalysis analysis={analysis} /> : null}

      {result ? <PortfolioResult result={result} /> : null}
    </div>
  );
}

function PortfolioAnalysis({ analysis }: { analysis: PickRow[] }) {
  const sorted = [...analysis].sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
  return (
    <div className="td-panel p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-2">
        <div className="text-[var(--td-ink-400)] text-[11px] uppercase tracking-wide">
          Path metrics by symbol
        </div>
        <div className="text-[var(--td-ink-400)] text-[11px]">
          Sorted by setup score · model path state only
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="scan-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Path label</th>
              <th>Setup</th>
              <th className="text-right">Score</th>
              <th className="text-right">Mark</th>
              <th className="text-right">Confidence</th>
              <th>Model</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => {
              const color = colorVarFor("action", row.action);
              return (
                <tr key={row.symbol}>
                  <td className="font-medium">{row.symbol}</td>
                  <td className="text-[12px] font-medium" style={{ color }}>
                    {row.action ?? row.error ?? "—"}
                  </td>
                  <td className="text-[12px] text-[var(--td-ink-300)]">
                    {row.setup_kind ?? "—"}
                  </td>
                  <td className="tabular text-right">{formatNum(row.score ?? 0, 3)}</td>
                  <td className="tabular text-right">{row.price ? formatUsd(row.price) : "—"}</td>
                  <td className="tabular text-right">{formatPct(row.confidence ?? 0, 0)}</td>
                  <td className="text-[11px] font-mono text-[var(--td-ink-300)]">
                    {row.model ?? "auto"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="mt-2 text-[var(--td-ink-400)] text-[11px]">
        Labels and scores come from the current model path (structure, filters, meta).
        Higher score ≠ instruction to size up; compare columns side by side.
      </div>
    </div>
  );
}

function PortfolioResult({ result }: { result: PortfolioOptimizationResponse }) {
  const [selected, setSelected] = useState<"max_sharpe" | "min_variance" | "equal_risk_contribution" | "inverse_volatility" | "equal_weight">("max_sharpe");

  const strategy =
    selected === "max_sharpe"
      ? result.mpt?.max_sharpe
      : selected === "min_variance"
      ? result.mpt?.min_variance
      : selected === "equal_risk_contribution"
      ? result.risk_parity?.equal_risk_contribution
      : selected === "inverse_volatility"
      ? result.risk_parity?.inverse_volatility
      : result.risk_parity?.equal_weight;

  const rows = result.symbols.map((symbol) => ({
    symbol,
    current: result.current_weights[symbol] ?? 0,
    price: result.last_prices[symbol] ?? 0,
    currentValue: result.market_values[symbol] ?? 0,
    target: strategy?.weights[symbol] ?? 0,
    rebal: strategy?.rebalancing[symbol],
  }));

  return (
    <div className="flex flex-col gap-3">
      <div className="td-panel p-3">
        <div className="text-[var(--td-ink-400)] text-[11px] uppercase tracking-wide mb-2">
          Current portfolio
        </div>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4 text-[12px]">
          <div>
            <div className="text-[var(--td-ink-400)]">Total value</div>
            <div className="tabular text-[var(--td-ink-100)]">{formatUsd(result.total_market_value)}</div>
          </div>
          <div>
            <div className="text-[var(--td-ink-400)]">Risk-free</div>
            <div className="tabular text-[var(--td-ink-100)]">{formatPct(result.risk_free, 2)}</div>
          </div>
          <div>
            <div className="text-[var(--td-ink-400)]">Lookback</div>
            <div className="tabular text-[var(--td-ink-100)]">{result.lookback}d</div>
          </div>
          <div>
            <div className="text-[var(--td-ink-400)]">Symbols</div>
            <div className="tabular text-[var(--td-ink-100)]">{result.symbols.length}</div>
          </div>
        </div>
      </div>

      <div className="td-panel p-3">
        <div className="flex flex-wrap gap-2 mb-3">
          {[
            { key: "max_sharpe", label: "Max Sharpe" },
            { key: "min_variance", label: "Min Variance" },
            { key: "equal_risk_contribution", label: "Risk Parity (ERC)" },
            { key: "inverse_volatility", label: "Inv Vol" },
            { key: "equal_weight", label: "Equal Weight" },
          ].map((opt) => (
            <button
              key={opt.key}
              className={`td-btn ${selected === opt.key ? "td-btn-primary" : "td-btn-ghost"}`}
              onClick={() => setSelected(opt.key as typeof selected)}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {strategy ? (
          <div className="overflow-x-auto">
            <table className="scan-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th className="text-right">Current wt</th>
                  <th className="text-right">Scenario wt</th>
                  <th className="text-right">Δ wt</th>
                  <th className="text-right">Δ $</th>
                  <th className="text-right">Δ shares</th>
                  <th className="text-right">Mark</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const rebal = r.rebal;
                  return (
                    <tr key={r.symbol}>
                      <td className="font-medium">{r.symbol}</td>
                      <td className="tabular text-right">{formatPct(r.current, 1)}</td>
                      <td className="tabular text-right">{formatPct(r.target, 1)}</td>
                      <td className="tabular text-right">{formatPct(rebal?.delta_weight ?? 0, 1)}</td>
                      <td className="tabular text-right">{formatUsd(rebal?.delta_dollar ?? 0)}</td>
                      <td className="tabular text-right">{formatNum(rebal?.shares_to_trade ?? 0, 2)}</td>
                      <td className="tabular text-right">{formatUsd(r.price)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div className="mt-3 text-[12px] text-[var(--td-ink-200)]">
              {selected === "max_sharpe" || selected === "min_variance" ? (
                <span>
                  Scenario ret {formatPct(strategy?.return, 1)} · vol {formatPct(strategy?.risk, 1)} · Sharpe {formatNum(strategy?.sharpe, 2)}
                  <span className="text-[var(--td-ink-400)]"> · mean-variance math on lookback window</span>
                </span>
              ) : (
                <span>
                  Scenario vol {formatPct(strategy?.risk, 1)} · risk contrib{" "}
                  {Object.entries(strategy?.risk_contribution || {})
                    .map(([k, v]) => `${k} ${formatPct(v, 0)}`)
                    .join(" / ")}
                </span>
              )}
            </div>
          </div>
        ) : null}
      </div>

      <details className="td-details td-details--block">
        <summary className="td-details__summary">Annualized metrics</summary>
        <div className="overflow-x-auto mt-2">
          <table className="scan-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th className="text-right">Return</th>
                <th className="text-right">Vol</th>
                {result.symbols.map((s) => (
                  <th key={s} className="text-right">{s}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.symbols.map((s) => (
                <tr key={s}>
                  <td className="font-medium">{s}</td>
                  <td className="tabular text-right">{formatPct(result.annualized.returns[s], 1)}</td>
                  <td className="tabular text-right">{formatPct(result.annualized.vols[s], 1)}</td>
                  {result.symbols.map((s2) => {
                    const idx1 = result.symbols.indexOf(s);
                    const idx2 = result.symbols.indexOf(s2);
                    return (
                      <td key={s2} className="tabular text-right">
                        {formatNum(result.annualized.correlation[idx1][idx2], 2)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
