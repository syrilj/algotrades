"use client";

import { useEffect, useState } from "react";

import { ActionChip } from "@/components/ui/ActionChip";
import { formatNum, formatPct, formatUsd } from "@/lib/format";
import type { ApiEnvelope, RiskAssessmentResponse } from "@/lib/types";

type RiskAssessmentPanelProps = {
  symbol: string;
  account?: number;
  equity?: number;
  peak?: number;
  returns?: number[];
  closedPnl?: number[];
};

export function RiskAssessmentPanel({
  symbol,
  account,
  equity,
  peak,
  returns,
  closedPnl,
}: RiskAssessmentPanelProps) {
  const [data, setData] = useState<RiskAssessmentResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!symbol || !account || account <= 0) {
      setData(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    const payload: Record<string, unknown> = {
      account,
      equity: equity ?? account,
      peak: peak ?? Math.max(account, equity ?? account),
      returns: returns ?? [],
      closed_pnl: closedPnl ?? [],
    };

    fetch("/api/risk-assessment", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then((r) => r.json())
      .then((json: ApiEnvelope<RiskAssessmentResponse>) => {
        if (!json.ok || !json.data) {
          throw new Error(json.error || "risk assessment failed");
        }
        if (!cancelled) {
          setData(json.data);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [symbol, account, equity, peak, returns, closedPnl]);

  if (!symbol) return null;

  return (
    <div className="td-panel p-3">
      <div className="mb-2 flex items-center justify-between">
        <span
          className="text-[11px] font-semibold tracking-wide"
          style={{ color: "var(--td-ink-300)" }}
        >
          RISK ASSESSMENT ·{" "}
          <span style={{ fontFamily: "var(--td-font-mono)", color: "var(--td-ink-100)" }}>
            {symbol}
          </span>
        </span>
        {loading ? (
          <span className="text-[10px]" style={{ color: "var(--td-ink-500)" }}>
            loading…
          </span>
        ) : data ? (
          <ActionChip action={data.mode} size="sm" />
        ) : null}
      </div>

      {error ? (
        <div className="td-alert td-alert--error" role="alert">
          {error}
        </div>
      ) : null}

      {data ? (
        <div className="flex flex-col gap-2 text-[12px]">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label="Drawdown" value={formatPct(data.drawdown, 1)} />
            <Stat label="Max DD" value={formatPct(data.drawdown_metrics.max, 1)} />
            <Stat label="Avg DD" value={formatPct(data.drawdown_metrics.average, 1)} />
            <Stat label="DD duration" value={`${data.drawdown_metrics.max_duration_days}d`} />
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label="Kelly full" value={formatPct(data.kelly.full, 1)} />
            <Stat label="Half Kelly" value={formatPct(data.kelly.half, 1)} />
            <Stat label="Half $" value={formatUsd(data.kelly.half_dollar, 0)} />
            <Stat label="Fixed shares" value={formatNum(data.position_sizing.fixed_fractional.shares, 2)} />
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label="VaR (p)" value={formatUsd(data.var_es.parametric.var, 0)} />
            <Stat label="ES (p)" value={formatUsd(data.var_es.parametric.es, 0)} />
            <Stat label="VaR (h)" value={formatUsd(data.var_es.historical.var, 0)} />
            <Stat label="ES (h)" value={formatUsd(data.var_es.historical.es, 0)} />
          </div>

          <div className="grid grid-cols-3 gap-2">
            <Stat label="Sharpe" value={formatNum(data.risk_adjusted.sharpe, 2)} />
            <Stat label="Sortino" value={formatNum(data.risk_adjusted.sortino, 2)} />
            <Stat label="Calmar" value={formatNum(data.risk_adjusted.calmar, 2)} />
          </div>

          {data.portfolio.std > 0 ? (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Stat label="Port variance" value={formatNum(data.portfolio.variance, 4)} />
              <Stat label="Port std" value={formatNum(data.portfolio.std, 4)} />
              <Stat
                label="Div benefit"
                value={formatPct(data.portfolio.diversification_benefit_pct / 100, 1)}
              />
            </div>
          ) : null}

          {data.reasons.length > 0 ? (
            <ul
              className="mt-1 flex flex-col gap-0.5 border-t pt-2 text-[11px]"
              style={{ borderColor: "var(--td-ink-700)", color: "var(--td-ink-400)" }}
            >
              {data.reasons.map((r, i) => (
                <li key={`${i}-${r.slice(0, 32)}`}>{r}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : (
        <p className="text-[12px]" style={{ color: "var(--td-ink-500)" }}>
          {loading ? "Computing risk metrics…" : "No risk data for this symbol."}
        </p>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px]" style={{ color: "var(--td-ink-500)" }}>
        {label}
      </span>
      <span
        className="tabular font-medium"
        style={{ fontFamily: "var(--td-font-mono)", color: "var(--td-ink-200)" }}
      >
        {value}
      </span>
    </div>
  );
}
